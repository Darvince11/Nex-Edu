# Edge protection: AWS WAF (managed rules, rate limits, bot control on login),
# attached to CloudFront. Shield Standard is automatic.

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0", configuration_aliases = [aws.us_east_1] }
  }
}

variable "environment" { type = string }
variable "login_rate_limit_per_5m" {
  type    = number
  default = 100
}
variable "global_rate_limit_per_5m" {
  type    = number
  default = 3000
}

locals {
  managed_rules = {
    AWSManagedRulesAmazonIpReputationList = 10
    AWSManagedRulesCommonRuleSet          = 20
    AWSManagedRulesKnownBadInputsRuleSet  = 30
    AWSManagedRulesSQLiRuleSet            = 40
  }
}

# CloudFront WAF ACLs must live in us-east-1.
resource "aws_wafv2_web_acl" "this" {
  provider = aws.us_east_1
  name     = "nexedu-${var.environment}"
  scope    = "CLOUDFRONT"

  default_action {
    allow {}
  }

  dynamic "rule" {
    for_each = local.managed_rules
    content {
      name     = rule.key
      priority = rule.value
      override_action {
        none {}
      }
      statement {
        managed_rule_group_statement {
          vendor_name = "AWS"
          name        = rule.key
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = rule.key
        sampled_requests_enabled   = true
      }
    }
  }

  rule {
    name     = "login-rate-limit"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = var.login_rate_limit_per_5m
        aggregate_key_type = "IP"
        scope_down_statement {
          byte_match_statement {
            search_string         = "/_allauth/"
            positional_constraint = "STARTS_WITH"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "login-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "global-rate-limit"
    priority = 2
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = var.global_rate_limit_per_5m
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "global-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "bot-control-on-auth"
    priority = 50
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesBotControlRuleSet"
        scope_down_statement {
          byte_match_statement {
            search_string         = "/_allauth/"
            positional_constraint = "STARTS_WITH"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "bot-control"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "nexedu-${var.environment}"
    sampled_requests_enabled   = true
  }
}

output "web_acl_arn" { value = aws_wafv2_web_acl.this.arn }
