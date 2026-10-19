# Account-level detective controls and ransomware-resistant backups.
# Apply once per workload account (staging, production).

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "environment" { type = string }
variable "backup_vault_kms_key_arn" { type = string }
variable "dr_backup_vault_arn" {
  type        = string
  description = "Vault in the DR region / backup account that receives daily copies"
}
variable "alert_email" { type = string }

resource "aws_guardduty_detector" "this" {
  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"
}

resource "aws_guardduty_detector_feature" "features" {
  for_each    = toset(["S3_DATA_EVENTS", "RDS_LOGIN_EVENTS", "RUNTIME_MONITORING", "MALWARE_PROTECTION"])
  detector_id = aws_guardduty_detector.this.id
  name        = each.key
  status      = "ENABLED"
}

resource "aws_securityhub_account" "this" {}

resource "aws_securityhub_standards_subscription" "fsbp" {
  depends_on    = [aws_securityhub_account.this]
  standards_arn = "arn:aws:securityhub:${data.aws_region.current.region}::standards/aws-foundational-security-best-practices/v/1.0.0"
}

resource "aws_securityhub_standards_subscription" "cis" {
  depends_on    = [aws_securityhub_account.this]
  standards_arn = "arn:aws:securityhub:${data.aws_region.current.region}::standards/cis-aws-foundations-benchmark/v/3.0.0"
}

resource "aws_inspector2_enabler" "this" {
  account_ids    = [data.aws_caller_identity.current.account_id]
  resource_types = ["ECR", "LAMBDA"]
}

resource "aws_accessanalyzer_analyzer" "this" {
  analyzer_name = "nexedu-${var.environment}"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# --- Backups: locked vault, daily copies to the DR vault -------------------

resource "aws_backup_vault" "primary" {
  name        = "nexedu-${var.environment}"
  kms_key_arn = var.backup_vault_kms_key_arn
}

# Compliance-mode lock: once the grace period passes, nobody (including root)
# can delete recovery points early or shorten retention.
resource "aws_backup_vault_lock_configuration" "primary" {
  backup_vault_name   = aws_backup_vault.primary.name
  min_retention_days  = 35
  max_retention_days  = 400
  changeable_for_days = 3
}

resource "aws_backup_plan" "tier1" {
  name = "nexedu-${var.environment}-tier1"

  rule {
    rule_name                = "daily"
    target_vault_name        = aws_backup_vault.primary.name
    schedule                 = "cron(0 1 * * ? *)"
    enable_continuous_backup = true
    lifecycle {
      delete_after = 35
    }
    copy_action {
      destination_vault_arn = var.dr_backup_vault_arn
      lifecycle {
        delete_after = 90
      }
    }
  }

  rule {
    rule_name         = "monthly"
    target_vault_name = aws_backup_vault.primary.name
    schedule          = "cron(0 2 1 * ? *)"
    lifecycle {
      cold_storage_after = 30
      delete_after       = 395
    }
  }
}

resource "aws_iam_role" "backup" {
  name = "nexedu-${var.environment}-backup"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "backup.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_selection" "tier1" {
  name         = "tier1-tagged"
  plan_id      = aws_backup_plan.tier1.id
  iam_role_arn = aws_iam_role.backup.arn
  selection_tag {
    type  = "STRINGEQUALS"
    key   = "nexedu:backup"
    value = "tier1"
  }
}

# --- Alerting --------------------------------------------------------------

# EventBridge can't publish to topics encrypted with the AWS-managed SNS key, so
# this topic uses SSE with a customer key whose policy admits events.amazonaws.com.
resource "aws_sns_topic" "security" {
  name              = "nexedu-${var.environment}-security-alerts"
  kms_master_key_id = var.backup_vault_kms_key_arn
}

resource "aws_sns_topic_policy" "security" {
  arn = aws_sns_topic.security.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowEventBridge"
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.security.arn
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.security.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_event_rule" "guardduty_high" {
  name = "nexedu-${var.environment}-guardduty-high"
  event_pattern = jsonencode({
    source        = ["aws.guardduty"]
    "detail-type" = ["GuardDuty Finding"]
    detail        = { severity = [{ numeric = [">=", 7] }] }
  })
}

resource "aws_cloudwatch_event_target" "guardduty_high" {
  rule = aws_cloudwatch_event_rule.guardduty_high.name
  arn  = aws_sns_topic.security.arn
}

output "security_topic_arn" { value = aws_sns_topic.security.arn }
