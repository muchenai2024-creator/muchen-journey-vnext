locals {
  common_tags = [
    { key = "system", value = "journey-next" },
    { key = "environment", value = "staging" },
    { key = "managed-by", value = "terraform" },
    { key = "candidate", value = substr(var.candidate_commit, 0, 12) },
  ]
}

resource "volcenginecc_vpc_vpc" "staging" {
  vpc_name     = "${var.resource_prefix}-vpc"
  cidr_block   = "10.88.0.0/16"
  project_name = var.project_name
  enable_ipv_6 = false
  tags         = local.common_tags
}

resource "volcenginecc_vpc_subnet" "app" {
  vpc_id      = volcenginecc_vpc_vpc.staging.vpc_id
  zone_id     = var.primary_zone_id
  subnet_name = "${var.resource_prefix}-app"
  cidr_block  = "10.88.10.0/24"
  tags        = local.common_tags
}

resource "volcenginecc_vpc_security_group" "app" {
  vpc_id              = volcenginecc_vpc_vpc.staging.vpc_id
  security_group_name = "${var.resource_prefix}-app"
  project_name        = var.project_name
  description         = "journey next staging web ingress and ephemeral deploy access"
  ingress_permissions = [
    {
      direction       = "ingress"
      policy          = "accept"
      protocol        = "tcp"
      port_start      = 80
      port_end        = 80
      priority        = 10
      cidr_ip         = "0.0.0.0/0"
      description     = "ACME redirect only"
    },
    {
      direction       = "ingress"
      policy          = "accept"
      protocol        = "tcp"
      port_start      = 443
      port_end        = 443
      priority        = 10
      cidr_ip         = "0.0.0.0/0"
      description     = "staging HTTPS"
    },
    {
      direction       = "ingress"
      policy          = "accept"
      protocol        = "tcp"
      port_start      = 22
      port_end        = 22
      priority        = 5
      cidr_ip         = var.deploy_cidr
      description     = "ephemeral GitHub runner only"
    },
  ]
  tags = local.common_tags
}

resource "volcenginecc_rdspostgresql_allow_list" "app" {
  allow_list_name     = "${replace(var.resource_prefix, "-", "_")}_app"
  allow_list_desc     = "journey next staging ECS security group only"
  allow_list_type     = "IPv4"
  allow_list_category = "Ordinary"
  security_group_bind_infos = [
    {
      bind_mode           = "AssociateEcsIp"
      security_group_id   = volcenginecc_vpc_security_group.app.security_group_id
      security_group_name = "${var.resource_prefix}-app"
      ip_list             = []
    },
  ]
}

resource "volcenginecc_rdspostgresql_instance" "staging" {
  instance_name     = "${var.resource_prefix}-postgres"
  db_engine_version = "PostgreSQL_17"
  storage_type      = "LocalSSD"
  storage_space     = var.rds_storage_gib
  vpc_id            = volcenginecc_vpc_vpc.staging.vpc_id
  subnet_id         = volcenginecc_vpc_subnet.app.subnet_id
  project_name      = var.project_name
  allow_list_ids    = [volcenginecc_rdspostgresql_allow_list.app.allow_list_id]
  charge_detail = {
    charge_type = "PostPaid"
  }
  node_info = [
    {
      zone_id   = var.primary_zone_id
      node_spec = var.rds_node_spec
      node_type = "Primary"
    },
    {
      zone_id   = var.secondary_zone_id
      node_spec = var.rds_node_spec
      node_type = "Secondary"
    },
  ]
  tags = local.common_tags
}

resource "volcenginecc_rdspostgresql_instance_ssl" "staging" {
  instance_id      = volcenginecc_rdspostgresql_instance.staging.instance_id
  force_encryption = true
}

resource "volcenginecc_rdspostgresql_db_account" "migration" {
  instance_id        = volcenginecc_rdspostgresql_instance.staging.instance_id
  account_name       = "journey_next_migrator"
  account_password   = var.migration_db_password
  account_type       = "Normal"
  account_privileges = "Login,Inherit"
}

resource "volcenginecc_rdspostgresql_db_account" "runtime" {
  instance_id          = volcenginecc_rdspostgresql_instance.staging.instance_id
  account_name         = "journey_next_runtime"
  account_password     = var.runtime_db_password
  account_type         = "Normal"
  account_privileges   = "Login,Inherit"
  not_allow_privileges = ["DDL"]
}

resource "volcenginecc_rdspostgresql_database" "staging" {
  instance_id        = volcenginecc_rdspostgresql_instance.staging.instance_id
  db_name            = "journey_next_staging"
  character_set_name = "utf8"
  collate            = "C.UTF-8"
  c_type             = "C.UTF-8"
  owner              = volcenginecc_rdspostgresql_db_account.migration.account_name
}

resource "volcenginecc_tos_bucket" "attachments" {
  name                  = var.tos_bucket_name
  project_name          = var.project_name
  storage_class         = "STANDARD"
  bucket_type           = "fns"
  az_redundancy         = "single-az"
  enable_version_status = "Enabled"
  acl_grant = {
    acl = "private"
  }
  lifecycle_config = [
    {
      lifecycle_rule_id = "abort-incomplete-uploads"
      status            = "Enabled"
      prefix            = "attachments/"
      abort_in_complete_multipart_upload = {
        days_after_initiation = 7
      }
    },
  ]
  tags = local.common_tags
}

resource "volcenginecc_tos_bucket_encryption" "attachments" {
  name          = volcenginecc_tos_bucket.attachments.name
  sse_algorithm = "AES256"
}

resource "volcenginecc_ecs_instance" "app" {
  instance_name             = "${var.resource_prefix}-app"
  hostname                  = "journey-next-staging"
  description               = "journey next isolated staging web api worker"
  project_name              = var.project_name
  instance_charge_type      = "PostPaid"
  instance_type             = var.ecs_instance_type
  zone_id                   = var.primary_zone_id
  deletion_protection       = true
  install_run_command_agent = true
  stopped_mode              = "StopCharging"
  spot_strategy             = "NoSpot"
  image = {
    image_id                      = var.ecs_image_id
    security_enhancement_strategy = "Active"
  }
  primary_network_interface = {
    subnet_id          = volcenginecc_vpc_subnet.app.subnet_id
    vpc_id             = volcenginecc_vpc_vpc.staging.vpc_id
    security_group_ids = [volcenginecc_vpc_security_group.app.security_group_id]
  }
  eip_address = {
    charge_type           = "PayByTraffic"
    bandwidth_mbps        = 5
    isp                   = "BGP"
    release_with_instance = true
  }
  system_volume = {
    size                 = var.ecs_system_volume_gib
    delete_with_instance = true
    volume_type          = "ESSD_PL0"
  }
  user_data = base64encode(<<-CLOUD_INIT
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v apt-get >/dev/null 2>&1; then
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y ca-certificates curl docker.io docker-compose-v2 openssl
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y ca-certificates curl docker docker-compose-plugin openssl
    else
      echo 'Unsupported base image package manager' >&2
      exit 1
    fi
    install -d -m 0700 -o root -g root /root/.ssh
    cat > /root/.ssh/authorized_keys <<'WP08_DEPLOY_PUBLIC_KEY'
    ${var.ecs_ssh_public_key}
    WP08_DEPLOY_PUBLIC_KEY
    chmod 0600 /root/.ssh/authorized_keys
    systemctl enable --now docker
    install -d -m 0750 -o root -g root /srv/journey-next-staging/releases
    install -d -m 0700 -o root -g root /srv/journey-next-staging/secrets
    install -d -m 0750 -o root -g root /srv/journey-next-staging/attachments
    printf '%s\n' '${var.candidate_commit}' >/srv/journey-next-staging/EXPECTED_CANDIDATE
  CLOUD_INIT
  )
  tags = local.common_tags

  lifecycle {
    precondition {
      condition     = var.approved_monthly_estimate_cny <= var.monthly_budget_cny
      error_message = "The verified calculator quote exceeds the authorized CNY 800 monthly budget."
    }
  }
}

resource "volcenginecc_dns_record" "staging" {
  zid    = var.dns_zone_id
  host   = var.dns_host
  type   = "A"
  value  = volcenginecc_ecs_instance.app.eip_address.ip_address
  line   = "default"
  ttl    = 600
  enable = true
  remark = "vNext staging"
}
