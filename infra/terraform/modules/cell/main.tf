# A "cell": one Aurora PostgreSQL Serverless v2 cluster holding ~25 school
# databases, fronted by PgBouncer. Cells bound the blast radius of a database
# incident and let capacity grow by adding cells, not by resizing one giant DB.

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "data_subnet_ids" { type = list(string) }
variable "app_security_group_id" { type = string }
variable "kms_key_arn" { type = string }
variable "engine_version" {
  type    = string
  default = "17.6"
}
variable "min_acu" {
  type    = number
  default = 2
}
variable "max_acu" {
  type    = number
  default = 32
}
variable "reader_count" {
  type    = number
  default = 1
}
variable "backup_retention_days" {
  type    = number
  default = 35
}
variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  id = "nexedu-${var.environment}-cell-${var.name}"
}

resource "aws_db_subnet_group" "this" {
  name       = local.id
  subnet_ids = var.data_subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "db" {
  name        = "${local.id}-db"
  description = "Aurora cell ${var.name}: reachable only from PgBouncer and migration tasks"
  vpc_id      = var.vpc_id
  tags        = var.tags
}

resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = var.app_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from app tier (PgBouncer, migrations, provisioning)"
}

resource "aws_rds_cluster_parameter_group" "this" {
  name   = local.id
  family = "aurora-postgresql${split(".", var.engine_version)[0]}"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "password_encryption"
    value = "scram-sha-256"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
  # Don't log statements: they can carry personal data.
  parameter {
    name  = "log_statement"
    value = "ddl"
  }
  parameter {
    name  = "pgaudit.log"
    value = "role,ddl"
  }
  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_stat_statements,pgaudit"
    apply_method = "pending-reboot"
  }
  tags = var.tags
}

resource "aws_rds_cluster" "this" {
  cluster_identifier                  = local.id
  engine                              = "aurora-postgresql"
  engine_mode                         = "provisioned"
  engine_version                      = var.engine_version
  database_name                       = "postgres"
  master_username                     = "nexedu_admin"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = var.kms_key_arn
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [aws_security_group.db.id]
  db_cluster_parameter_group_name     = aws_rds_cluster_parameter_group.this.name
  storage_encrypted                   = true
  kms_key_id                          = var.kms_key_arn
  iam_database_authentication_enabled = true
  backup_retention_period             = var.backup_retention_days
  preferred_backup_window             = "01:00-02:00"
  preferred_maintenance_window        = "sun:02:30-sun:03:30"
  copy_tags_to_snapshot               = true
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${local.id}-final"
  enabled_cloudwatch_logs_exports     = ["postgresql"]

  serverlessv2_scaling_configuration {
    min_capacity = var.min_acu
    max_capacity = var.max_acu
  }
  tags = merge(var.tags, { "nexedu:cell" = var.name, "nexedu:backup" = "tier1" })
}

resource "aws_rds_cluster_instance" "writer" {
  identifier                            = "${local.id}-writer"
  cluster_identifier                    = aws_rds_cluster.this.id
  instance_class                        = "db.serverless"
  engine                                = aws_rds_cluster.this.engine
  engine_version                        = aws_rds_cluster.this.engine_version
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.kms_key_arn
  performance_insights_retention_period = 7
  auto_minor_version_upgrade            = true
  tags                                  = var.tags
}

# Readers live in other AZs; Aurora promotes one automatically on writer failure.
resource "aws_rds_cluster_instance" "reader" {
  count                        = var.reader_count
  identifier                   = "${local.id}-reader-${count.index + 1}"
  cluster_identifier           = aws_rds_cluster.this.id
  instance_class               = "db.serverless"
  engine                       = aws_rds_cluster.this.engine
  engine_version               = aws_rds_cluster.this.engine_version
  performance_insights_enabled = true
  promotion_tier               = 1
  auto_minor_version_upgrade   = true
  tags                         = var.tags
}

output "cluster_id" { value = aws_rds_cluster.this.id }
output "writer_endpoint" { value = aws_rds_cluster.this.endpoint }
output "reader_endpoint" { value = aws_rds_cluster.this.reader_endpoint }
output "admin_secret_arn" { value = aws_rds_cluster.this.master_user_secret[0].secret_arn }
output "db_security_group_id" { value = aws_security_group.db.id }
