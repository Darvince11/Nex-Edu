# One Fargate service: least-privilege IAM, read-only root filesystem, non-root
# user, secrets injected from Secrets Manager, CPU-based autoscaling.

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" { type = string }
variable "cluster_arn" { type = string }
variable "image" { type = string }
variable "command" {
  type    = list(string)
  default = []
}
variable "port" {
  type    = number
  default = null
}
variable "cpu" { type = number }
variable "memory" { type = number }
variable "min_count" { type = number }
variable "max_count" { type = number }
variable "subnet_ids" { type = list(string) }
variable "security_group_ids" { type = list(string) }
variable "kms_key_arn" { type = string }
variable "field_kms_key_arn" { type = string }
variable "files_bucket_arn" { type = string }
variable "queue_arns" { type = list(string) }
variable "environment" { type = map(string) }
variable "secrets" {
  type      = map(string)
  sensitive = true
}
variable "target_group_arn" {
  type    = string
  default = null
}
variable "discovery_namespace_id" {
  type        = string
  default     = null
  description = "Cloud Map namespace; registers <name>.<namespace> for internal callers"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  id = "nexedu-production-${var.name}"
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/nexedu/production/${var.name}"
  retention_in_days = 90
  kms_key_id        = var.kms_key_arn
}

resource "aws_iam_role" "execution" {
  name = "${local.id}-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = values(nonsensitive(var.secrets)) },
      { Effect = "Allow", Action = "kms:Decrypt", Resource = var.kms_key_arn },
    ]
  })
}

# What the application itself may do. School DB secrets are under a fixed
# prefix; the field key can only be used with an encryption context naming a school.
resource "aws_iam_role" "task" {
  name = "${local.id}-task"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SchoolDbSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "secretsmanager:CreateSecret", "secretsmanager:PutSecretValue", "secretsmanager:TagResource"]
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:nexedu/prod/tenants/*"
      },
      {
        Sid       = "FieldKeys"
        Effect    = "Allow"
        Action    = ["kms:GenerateDataKey", "kms:Decrypt"]
        Resource  = var.field_kms_key_arn
        Condition = { "ForAnyValue:StringLike" = { "kms:EncryptionContextKeys" = ["tenant_id"] } }
      },
      { Sid = "DataKey", Effect = "Allow", Action = ["kms:GenerateDataKey", "kms:Decrypt"], Resource = var.kms_key_arn },
      {
        Sid      = "Files"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${var.files_bucket_arn}/tenants/*"
      },
      {
        Sid      = "Queues"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
        Resource = var.queue_arns
      },
    ]
  })
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.id
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }
  volume {
    name = "tmp"
  }
  container_definitions = jsonencode([{
    name                   = var.name
    image                  = var.image
    command                = length(var.command) > 0 ? var.command : null
    essential              = true
    readonlyRootFilesystem = true
    user                   = "10001:10001"
    linuxParameters        = { capabilities = { drop = ["ALL"] }, initProcessEnabled = true }
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
    portMappings           = var.port == null ? [] : [{ containerPort = var.port, protocol = "tcp" }]
    environment            = [for k, v in var.environment : { name = k, value = v }]
    secrets                = [for k, v in nonsensitive(var.secrets) : { name = k, valueFrom = v }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = var.name
      }
    }
  }])
}

resource "aws_ecs_service" "this" {
  name                   = var.name
  cluster                = var.cluster_arn
  task_definition        = aws_ecs_task_definition.this.arn
  desired_count          = var.min_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  dynamic "load_balancer" {
    for_each = var.target_group_arn == null ? [] : [1]
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.name
      container_port   = var.port
    }
  }
  dynamic "service_registries" {
    for_each = var.discovery_namespace_id == null ? [] : [1]
    content {
      registry_arn = aws_service_discovery_service.this[0].arn
    }
  }
  lifecycle {
    ignore_changes = [desired_count]
  }
}

resource "aws_service_discovery_service" "this" {
  count = var.discovery_namespace_id == null ? 0 : 1
  name  = var.name
  dns_config {
    namespace_id   = var.discovery_namespace_id
    routing_policy = "MULTIVALUE"
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
  health_check_custom_config {}
}

resource "aws_appautoscaling_target" "this" {
  service_namespace  = "ecs"
  resource_id        = "service/${element(split("/", var.cluster_arn), 1)}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.min_count
  max_capacity       = var.max_count
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${local.id}-cpu"
  service_namespace  = aws_appautoscaling_target.this.service_namespace
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  policy_type        = "TargetTrackingScaling"
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

output "service_name" { value = aws_ecs_service.this.name }
output "task_role_arn" { value = aws_iam_role.task.arn }
