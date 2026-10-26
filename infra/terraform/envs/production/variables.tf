variable "region" {
  type    = string
  default = "af-south-1"
}

variable "domain" {
  type        = string
  description = "Base domain; schools live at <slug>.<domain>"
  default     = "nexedu.com.gh"
}

variable "account_suffix" {
  type        = string
  description = "Makes globally unique bucket names"
}

variable "image_tag" {
  type        = string
  description = "Immutable image tag (git SHA) to deploy"
}

variable "cells" {
  type        = list(string)
  description = "Database cells. 100 schools at ~25 per cell = 4 cells, plus headroom."
  default     = ["a", "b", "c", "d", "e"]
}

variable "queues" {
  type    = list(string)
  default = ["default", "critical-payments", "notifications", "reports"]
}

variable "services" {
  type = map(object({
    repo    = string
    command = list(string)
    port    = optional(number)
    cpu     = number
    memory  = number
    min     = number
    max     = number
  }))
  default = {
    api = {
      repo = "api", command = [], port = 8000, cpu = 2048, memory = 4096, min = 4, max = 40
    }
    web = {
      repo = "web", command = [], port = 3000, cpu = 1024, memory = 2048, min = 2, max = 20
    }
    worker = {
      repo    = "api"
      command = ["celery", "-A", "config", "worker", "-Q", "default,reports", "--concurrency", "4"]
      cpu     = 2048, memory = 4096, min = 2, max = 30
    }
    worker-critical = {
      repo    = "api"
      command = ["celery", "-A", "config", "worker", "-Q", "critical-payments,notifications", "--concurrency", "8"]
      cpu     = 1024, memory = 2048, min = 2, max = 10
    }
    beat = {
      repo = "api", command = ["celery", "-A", "config", "beat"], cpu = 256, memory = 512, min = 1, max = 1
    }
  }
}

variable "service_secret_arns" {
  type        = map(string)
  description = "Env var name → Secrets Manager ARN (DJANGO_SECRET_KEY, CONTROL_DB_*, VALKEY_URL, HEADLESS_JWT_PRIVATE_KEY, ...)"
  sensitive   = true
}

variable "valkey_auth_token" {
  type      = string
  sensitive = true
}

variable "dr_backup_vault_arn" { type = string }
variable "security_alert_email" { type = string }

variable "origin_verify_secret" {
  type        = string
  sensitive   = true
  description = "Shared header value proving a request came through CloudFront (rotate quarterly)"
}

variable "pgbouncer_secret_arns" {
  type        = map(string)
  sensitive   = true
  description = "PGBOUNCER_AUTH_PASSWORD and TLS key/cert secret ARNs for the PgBouncer tasks"
}
