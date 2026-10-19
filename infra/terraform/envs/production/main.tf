# Production workload account, primary region af-south-1 (Cape Town).
# State lives in an S3 bucket with native locking in the shared-services account.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  backend "s3" {
    bucket       = "nexedu-terraform-state"
    key          = "production/terraform.tfstate"
    region       = "af-south-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { app = "nexedu", environment = "production", "data-classification" = "confidential-pii" }
  }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

locals {
  env  = "production"
  tags = { app = "nexedu", environment = local.env }
}

# --- Encryption keys --------------------------------------------------------

resource "aws_kms_key" "data" {
  description             = "Nex Edu production: Aurora, S3, SQS, backups"
  enable_key_rotation     = true
  rotation_period_in_days = 365
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "data" {
  name          = "alias/nexedu-production-data"
  target_key_id = aws_kms_key.data.key_id
}

# Wraps each school's field-encryption data key (encryption context = tenant id).
resource "aws_kms_key" "field" {
  description             = "Nex Edu production: per-school field encryption data keys"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

resource "aws_kms_alias" "field" {
  name          = "alias/nexedu-production-field"
  target_key_id = aws_kms_key.field.key_id
}

# --- Network, security baseline, edge ---------------------------------------

module "network" {
  source      = "../../modules/network"
  environment = local.env
  azs         = ["af-south-1a", "af-south-1b", "af-south-1c"]
  tags        = local.tags
}

module "security" {
  source                   = "../../modules/security-baseline"
  environment              = local.env
  backup_vault_kms_key_arn = aws_kms_key.data.arn
  dr_backup_vault_arn      = var.dr_backup_vault_arn
  alert_email              = var.security_alert_email
}

module "edge" {
  source      = "../../modules/edge"
  environment = local.env
  providers   = { aws.us_east_1 = aws.us_east_1 }
}

# --- Data cells (add a key to grow; each holds ~25 schools) ----------------

module "cell" {
  for_each              = toset(var.cells)
  source                = "../../modules/cell"
  name                  = each.key
  environment           = local.env
  vpc_id                = module.network.vpc_id
  data_subnet_ids       = module.network.data_subnet_ids
  app_security_group_id = aws_security_group.app.id
  kms_key_arn           = aws_kms_key.data.arn
  tags                  = local.tags
}

module "control_plane_db" {
  source                = "../../modules/cell"
  name                  = "control"
  environment           = local.env
  vpc_id                = module.network.vpc_id
  data_subnet_ids       = module.network.data_subnet_ids
  app_security_group_id = aws_security_group.app.id
  kms_key_arn           = aws_kms_key.data.arn
  reader_count          = 1
  tags                  = local.tags
}

# --- Valkey (cache, sessions, rate limits, realtime) ------------------------

resource "aws_elasticache_subnet_group" "valkey" {
  name       = "nexedu-production-valkey"
  subnet_ids = module.network.data_subnet_ids
}

resource "aws_security_group" "valkey" {
  name   = "nexedu-production-valkey"
  vpc_id = module.network.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "valkey_from_app" {
  security_group_id            = aws_security_group.valkey.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_elasticache_replication_group" "valkey" {
  replication_group_id       = "nexedu-production"
  description                = "Nex Edu cache, sessions and rate limits"
  engine                     = "valkey"
  engine_version             = "8.1"
  node_type                  = "cache.r7g.large"
  num_cache_clusters         = 3
  automatic_failover_enabled = true
  multi_az_enabled           = true
  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.data.arn
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  auth_token_update_strategy = "ROTATE"
  auth_token                 = var.valkey_auth_token
  subnet_group_name          = aws_elasticache_subnet_group.valkey.name
  security_group_ids         = [aws_security_group.valkey.id]
  snapshot_retention_limit   = 7
}

# --- Queues: separate queues so bulk work can't delay payments --------------

resource "aws_sqs_queue" "dlq" {
  for_each                  = toset(var.queues)
  name                      = "nexedu-production-${each.key}-dlq"
  kms_master_key_id         = aws_kms_key.data.arn
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "queue" {
  for_each                   = toset(var.queues)
  name                       = "nexedu-production-${each.key}"
  kms_master_key_id          = aws_kms_key.data.arn
  visibility_timeout_seconds = 900
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5
  })
}

# --- Object storage ---------------------------------------------------------

resource "aws_s3_bucket" "files" {
  bucket = "nexedu-production-files-${var.account_suffix}"
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_policy" "files_tls_only" {
  bucket = aws_s3_bucket.files.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.files.arn, "${aws_s3_bucket.files.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

# --- Compute ----------------------------------------------------------------

resource "aws_security_group" "alb" {
  name   = "nexedu-production-alb"
  vpc_id = module.network.vpc_id
}

# Only CloudFront may reach the load balancer.
data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_cloudfront" {
  security_group_id = aws_security_group.alb.id
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 8000
}

resource "aws_security_group" "app" {
  name        = "nexedu-production-app"
  description = "API, web, workers and PgBouncer tasks"
  vpc_id      = module.network.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "app_to_pgbouncer" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 6432
  to_port                      = 6432
}

resource "aws_vpc_security_group_egress_rule" "app_all" {
  security_group_id = aws_security_group.app.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_ecr_repository" "repo" {
  for_each             = toset(["api", "web", "pgbouncer"])
  name                 = "nexedu/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.data.arn
  }
}

resource "aws_ecs_cluster" "this" {
  name = "nexedu-production"
  setting {
    name  = "containerInsights"
    value = "enhanced"
  }
}

module "service" {
  for_each           = var.services
  source             = "../../modules/ecs-service"
  name               = each.key
  cluster_arn        = aws_ecs_cluster.this.arn
  image              = "${aws_ecr_repository.repo[each.value.repo].repository_url}:${var.image_tag}"
  command            = each.value.command
  port               = each.value.port
  cpu                = each.value.cpu
  memory             = each.value.memory
  min_count          = each.value.min
  max_count          = each.value.max
  subnet_ids         = module.network.app_subnet_ids
  security_group_ids = [aws_security_group.app.id]
  kms_key_arn        = aws_kms_key.data.arn
  field_kms_key_arn  = aws_kms_key.field.arn
  files_bucket_arn   = aws_s3_bucket.files.arn
  queue_arns         = [for q in aws_sqs_queue.queue : q.arn]
  environment = {
    AWS_REGION                      = var.region
    DJANGO_ALLOWED_HOSTS            = ".${var.domain}"
    TENANT_BASE_DOMAIN              = var.domain
    FIELD_ENCRYPTION_KMS_KEY_ID     = aws_kms_key.field.arn
    TENANT_SECRETS_KMS_KEY_ID       = aws_kms_key.data.arn
    SQS_QUEUE_URL_DEFAULT           = aws_sqs_queue.queue["default"].url
    SQS_QUEUE_URL_CRITICAL_PAYMENTS = aws_sqs_queue.queue["critical-payments"].url
    SQS_QUEUE_URL_NOTIFICATIONS     = aws_sqs_queue.queue["notifications"].url
    SQS_QUEUE_URL_REPORTS           = aws_sqs_queue.queue["reports"].url
  }
  secrets          = var.service_secret_arns
  target_group_arn = contains(["api", "web"], each.key) ? aws_lb_target_group.app[each.key].arn : null
}

# One PgBouncer service per cell, discoverable as pgbouncer-<cell>.nexedu.internal.
module "pgbouncer" {
  for_each               = toset(concat(var.cells, ["control"]))
  source                 = "../../modules/ecs-service"
  name                   = "pgbouncer-${each.key}"
  cluster_arn            = aws_ecs_cluster.this.arn
  image                  = "${aws_ecr_repository.repo["pgbouncer"].repository_url}:${var.image_tag}"
  port                   = 6432
  cpu                    = 512
  memory                 = 1024
  min_count              = 2
  max_count              = 6
  subnet_ids             = module.network.app_subnet_ids
  security_group_ids     = [aws_security_group.app.id]
  kms_key_arn            = aws_kms_key.data.arn
  field_kms_key_arn      = aws_kms_key.field.arn
  files_bucket_arn       = aws_s3_bucket.files.arn
  queue_arns             = []
  discovery_namespace_id = aws_service_discovery_private_dns_namespace.internal.id
  environment = {
    CELL_WRITER_ENDPOINT = each.key == "control" ? module.control_plane_db.writer_endpoint : module.cell[each.key].writer_endpoint
  }
  secrets = var.pgbouncer_secret_arns
}

output "cell_admin_secrets" {
  value = { for k, c in module.cell : k => c.admin_secret_arn }
}
