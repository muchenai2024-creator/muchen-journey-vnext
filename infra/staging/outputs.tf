output "ecs_instance_id" {
  value = volcenginecc_ecs_instance.app.instance_id
}

output "staging_public_ip" {
  value = volcenginecc_ecs_instance.app.eip_address.ip_address
}

output "staging_security_group_id" {
  value = volcenginecc_vpc_security_group.app.security_group_id
}

output "rds_private_host" {
  value = one(flatten([
    for endpoint in volcenginecc_rdspostgresql_instance.staging.endpoints : [
      for address in endpoint.address : address.domain
      if address.network_type == "Private"
    ]
  ]))
  sensitive = true
}

output "rds_private_port" {
  value = one(flatten([
    for endpoint in volcenginecc_rdspostgresql_instance.staging.endpoints : [
      for address in endpoint.address : address.port
      if address.network_type == "Private"
    ]
  ]))
}

output "tos_bucket_name" {
  value = volcenginecc_tos_bucket.attachments.name
}

output "staging_origin" {
  value = var.staging_origin
}
