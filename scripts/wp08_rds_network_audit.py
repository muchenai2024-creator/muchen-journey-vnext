#!/usr/bin/env python3
"""Compare frozen WP-08 ECS private IPs with the live RDS allowlist."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.wp08_dns_record import canonical_query, signed_headers


API_HOST = "rds-postgresql.cn-beijing.volcengineapi.com"
API_REGION = "cn-beijing"
API_SERVICE = "rds_postgresql"
API_VERSION = "2022-01-01"
STAGING_SUBNET = ipaddress.ip_network("10.88.10.0/24")
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9-]{7,80}$")


class NetworkAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class StateFacts:
    private_ips: frozenset[ipaddress.IPv4Address]
    vpc_id: str
    security_group_id: str
    allow_list_id: str
    rds_instance_id: str


def _attributes(state: dict[str, object], resource_type: str, name: str) -> dict[str, object]:
    resources = state.get("resources")
    if not isinstance(resources, list):
        raise NetworkAuditError("frozen Terraform state resources are missing")
    matches = [
        resource
        for resource in resources
        if isinstance(resource, dict)
        and resource.get("mode") == "managed"
        and resource.get("type") == resource_type
        and resource.get("name") == name
    ]
    if len(matches) != 1:
        raise NetworkAuditError(f"expected one {resource_type}.{name} state resource")
    instances = matches[0].get("instances")
    if not isinstance(instances, list) or len(instances) != 1:
        raise NetworkAuditError(f"expected one {resource_type}.{name} state instance")
    attributes = instances[0].get("attributes") if isinstance(instances[0], dict) else None
    if not isinstance(attributes, dict):
        raise NetworkAuditError(f"{resource_type}.{name} state attributes are missing")
    return attributes


def _private_ips(value: object) -> set[ipaddress.IPv4Address]:
    found: set[ipaddress.IPv4Address] = set()
    if isinstance(value, dict):
        for child in value.values():
            found.update(_private_ips(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_private_ips(child))
    elif isinstance(value, str):
        try:
            address = ipaddress.IPv4Address(value)
        except ipaddress.AddressValueError:
            return found
        if address in STAGING_SUBNET:
            found.add(address)
    return found


def _identifier(attributes: dict[str, object], key: str, label: str) -> str:
    value = attributes.get(key)
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise NetworkAuditError(f"{label} identifier is missing or invalid")
    return value


def state_facts(state: dict[str, object]) -> StateFacts:
    ecs = _attributes(state, "volcenginecc_ecs_instance", "app")
    network = ecs.get("primary_network_interface")
    private_ips = _private_ips(network)
    if not private_ips:
        raise NetworkAuditError("staging ECS private IP is absent from frozen state")
    vpc = _attributes(state, "volcenginecc_vpc_vpc", "staging")
    vpc_id = _identifier(vpc, "vpc_id", "VPC")
    if not isinstance(network, dict) or network.get("vpc_id") != vpc_id:
        raise NetworkAuditError("staging ECS primary NIC is not in the expected VPC")
    security_group = _attributes(state, "volcenginecc_vpc_security_group", "app")
    allow_list = _attributes(state, "volcenginecc_rdspostgresql_allow_list", "app")
    rds = _attributes(state, "volcenginecc_rdspostgresql_instance", "staging")
    return StateFacts(
        private_ips=frozenset(private_ips),
        vpc_id=vpc_id,
        security_group_id=_identifier(
            security_group, "security_group_id", "security group"
        ),
        allow_list_id=_identifier(allow_list, "allow_list_id", "allowlist"),
        rds_instance_id=_identifier(rds, "instance_id", "RDS instance"),
    )


def request_detail(
    allow_list_id: str,
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
) -> dict[str, object]:
    parameters = {"Action": "DescribeAllowListDetail", "Version": API_VERSION}
    body = json.dumps(
        {"AllowListId": allow_list_id}, separators=(",", ":")
    ).encode()
    request = Request(
        f"https://{API_HOST}/?{canonical_query(parameters)}",
        data=body,
        headers=signed_headers(
            parameters,
            access_key,
            secret_key,
            service=API_SERVICE,
            region=API_REGION,
            host=API_HOST,
            method="POST",
            body=body,
            content_type="application/json",
            session_token=session_token,
        ),
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS host
            raw = response.read(1_000_001)
    except HTTPError as error:
        raise NetworkAuditError(f"RDS API returned HTTP {error.code}") from error
    except URLError as error:
        raise NetworkAuditError("RDS API request failed") from error
    if len(raw) > 1_000_000:
        raise NetworkAuditError("RDS API response exceeded the safety limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NetworkAuditError("RDS API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise NetworkAuditError("RDS API response must be an object")
    metadata = payload.get("ResponseMetadata")
    if isinstance(metadata, dict) and metadata.get("Error"):
        api_error = metadata["Error"]
        code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        raise NetworkAuditError(f"RDS API rejected DescribeAllowListDetail ({code})")
    result = payload.get("Result")
    if not isinstance(result, dict):
        raise NetworkAuditError("RDS allowlist detail is missing")
    return result


def _host_ips(values: object) -> set[ipaddress.IPv4Address]:
    if not isinstance(values, list):
        raise NetworkAuditError("RDS security-group IP list is missing")
    found: set[ipaddress.IPv4Address] = set()
    for value in values:
        if not isinstance(value, str):
            raise NetworkAuditError("RDS security-group IP list is invalid")
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as error:
            raise NetworkAuditError("RDS security-group IP list is invalid") from error
        if network.version != 4 or network.prefixlen != 32:
            raise NetworkAuditError("RDS security-group binding contains a non-host network")
        found.add(network.network_address)
    return found


def validate_detail(detail: dict[str, object], facts: StateFacts) -> None:
    if detail.get("AllowListId") != facts.allow_list_id:
        raise NetworkAuditError("RDS API returned a different allowlist")
    bindings = detail.get("SecurityGroupBindInfos")
    if not isinstance(bindings, list):
        raise NetworkAuditError("RDS security-group binding is missing")
    matches = [
        binding
        for binding in bindings
        if isinstance(binding, dict)
        and binding.get("SecurityGroupId") == facts.security_group_id
        and binding.get("BindMode") == "AssociateEcsIp"
    ]
    if len(matches) != 1:
        raise NetworkAuditError("expected one exact RDS security-group binding")
    if _host_ips(matches[0].get("IpList")) != set(facts.private_ips):
        raise NetworkAuditError("RDS allowlist does not match the staging ECS private IP set")
    instances = detail.get("AssociatedInstances")
    if not isinstance(instances, list):
        raise NetworkAuditError("RDS allowlist instance association is missing")
    matches = [
        item
        for item in instances
        if isinstance(item, dict) and item.get("InstanceId") == facts.rds_instance_id
    ]
    if len(matches) != 1:
        raise NetworkAuditError("RDS allowlist is not associated with the staging instance")
    if matches[0].get("VPC") != facts.vpc_id:
        raise NetworkAuditError("RDS allowlist instance is not in the staging VPC")
    if matches[0].get("IsLatest") is not True:
        raise NetworkAuditError("RDS allowlist is not synchronized to the staging instance")


def audit(state_path: Path) -> None:
    access_key = os.environ.get("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.environ.get("VOLCENGINE_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise NetworkAuditError("Volcengine workflow credentials are missing")
    try:
        state = json.loads(state_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NetworkAuditError("frozen Terraform state is unreadable") from error
    if not isinstance(state, dict):
        raise NetworkAuditError("frozen Terraform state must be an object")
    facts = state_facts(state)
    detail = request_detail(
        facts.allow_list_id,
        access_key,
        secret_key,
        session_token=os.environ.get("VOLCENGINE_SESSION_TOKEN", ""),
    )
    validate_detail(detail, facts)
    print(
        "WP08_RDS_NETWORK_AUDIT=PASS"
        f" ecs_private_ip_count={len(facts.private_ips)}"
        " allowlist_match=true instance_association=true"
        " vpc_match=true allowlist_latest=true"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    audit(args.state)


if __name__ == "__main__":
    try:
        main()
    except NetworkAuditError as error:
        print(f"WP08_RDS_NETWORK_AUDIT_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
