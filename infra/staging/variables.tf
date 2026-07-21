variable "region_id" {
  description = "Volcengine region ID. WP-08 is approved only for cn-beijing."
  type        = string
  default     = "cn-beijing"

  validation {
    condition     = var.region_id == "cn-beijing"
    error_message = "WP-08 is authorized only for cn-beijing (华北2/北京)."
  }
}

variable "primary_zone_id" {
  description = "Inventory-verified primary AZ in cn-beijing."
  type        = string

  validation {
    condition     = startswith(var.primary_zone_id, "cn-beijing-")
    error_message = "primary_zone_id must belong to cn-beijing."
  }
}

variable "secondary_zone_id" {
  description = "Inventory-verified secondary RDS AZ in cn-beijing."
  type        = string

  validation {
    condition     = startswith(var.secondary_zone_id, "cn-beijing-")
    error_message = "secondary_zone_id must belong to cn-beijing."
  }
}

variable "project_name" {
  type    = string
  default = "journey-next-staging"
}

variable "resource_prefix" {
  type    = string
  default = "journey-next-staging"
}

variable "monthly_budget_cny" {
  type    = number
  default = 500

  validation {
    condition     = var.monthly_budget_cny == 500
    error_message = "WP-08 has an exact monthly ceiling of CNY 500."
  }
}

variable "approved_monthly_estimate_cny" {
  description = "Total copied from an itemized Volcengine calculator quote immediately before apply."
  type        = number

  validation {
    condition     = var.approved_monthly_estimate_cny > 0 && var.approved_monthly_estimate_cny <= 500
    error_message = "The verified monthly estimate must be positive and no more than CNY 500."
  }
}

variable "candidate_commit" {
  type    = string
  default = "ff07ce47d20f3f6eb09d633b09292628fbb58e2a"

  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.candidate_commit))
    error_message = "candidate_commit must be a full lowercase 40-character SHA."
  }
}

variable "staging_origin" {
  type    = string
  default = "https://staging-vnext.muchenai.com"

  validation {
    condition     = can(regex("^https://[a-z0-9.-]+$", var.staging_origin))
    error_message = "staging_origin must be one HTTPS origin without a path."
  }
}

variable "dns_zone_id" {
  description = "Delegated staging-vnext.muchenai.com child-zone ID created during main-account bootstrap."
  type        = string
}

variable "dns_host" {
  type    = string
  default = "@"
}

variable "ecs_image_id" {
  description = "Inventory-verified maintained veLinux/Ubuntu image ID."
  type        = string
}

variable "ecs_instance_type" {
  description = "Calculator-quoted ECS type with at least 2 vCPU and 4 GiB RAM."
  type        = string
}

variable "ecs_system_volume_gib" {
  type    = number
  default = 40

  validation {
    condition     = var.ecs_system_volume_gib >= 40 && var.ecs_system_volume_gib <= 100
    error_message = "The staging system volume must stay between 40 and 100 GiB."
  }
}

variable "ecs_ssh_public_key" {
  description = "Public half of the staging-only deploy key stored in the GitHub staging environment."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) ", var.ecs_ssh_public_key))
    error_message = "ecs_ssh_public_key must be an OpenSSH public key."
  }
}

variable "deploy_cidr" {
  description = "Ephemeral GitHub runner /32. Use 127.0.0.1/32 outside an active deployment."
  type        = string
  default     = "127.0.0.1/32"

  validation {
    condition     = can(cidrhost(var.deploy_cidr, 0)) && tonumber(split("/", var.deploy_cidr)[1]) == 32
    error_message = "deploy_cidr must be one IPv4 /32."
  }
}

variable "rds_node_spec" {
  description = "Calculator-quoted RDS PostgreSQL node specification."
  type        = string
  default     = "rds.postgres.1c2g"
}

variable "rds_storage_gib" {
  type    = number
  default = 20

  validation {
    condition     = var.rds_storage_gib >= 20 && var.rds_storage_gib <= 100 && var.rds_storage_gib % 10 == 0
    error_message = "RDS storage must be 20-100 GiB in 10 GiB increments."
  }
}

variable "migration_db_password" {
  description = "Generated staging-only migration credential sourced from GitHub Environment secrets."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.migration_db_password) >= 20 && length(var.migration_db_password) <= 32
    error_message = "RDS migration password must contain 20-32 characters."
  }
}

variable "runtime_db_password" {
  description = "Generated staging-only runtime credential sourced from GitHub Environment secrets."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.runtime_db_password) >= 20 && length(var.runtime_db_password) <= 32 && var.runtime_db_password != var.migration_db_password
    error_message = "Runtime password must be 20-32 characters and independent from migration password."
  }
}

variable "tos_bucket_name" {
  description = "Globally unique staging-only bucket name, without account IDs or other private identifiers."
  type        = string

  validation {
    condition     = startswith(var.tos_bucket_name, "journey-next-staging-")
    error_message = "The TOS bucket must use the journey-next-staging-* namespace."
  }
}
