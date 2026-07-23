#!/usr/bin/env python3
"""Open and close one exact WP-08 SSH rule without CloudControl."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.wp08_dns_record import API_HOST, canonical_query, signed_headers


API_REGION = "cn-beijing"
API_SERVICE = "vpc"
API_VERSION = "2020-04-01"
DESCRIPTION = "ephemeral GitHub runner only"
SECURITY_GROUP_ID = re.compile(r"^sg-[A-Za-z0-9]{8,64}$")


class SecurityGroupError(RuntimeError):
    pass


def rule_parameters(action: str, security_group_id: str, cidr: str) -> dict[str, str]:
    if action not in {
        "AuthorizeSecurityGroupIngress",
        "RevokeSecurityGroupIngress",
        "DescribeSecurityGroupAttributes",
    }:
        raise SecurityGroupError("unsupported VPC action")
    if not SECURITY_GROUP_ID.fullmatch(security_group_id):
        raise SecurityGroupError("security group identifier is invalid")
    try:
        network = ipaddress.ip_network(cidr, strict=True)
    except ValueError as error:
        raise SecurityGroupError("runner CIDR is invalid") from error
    if network.version != 4 or network.prefixlen != 32 or not network.network_address.is_global:
        raise SecurityGroupError("runner CIDR must be one public IPv4 /32")

    parameters = {
        "Action": action,
        "Version": API_VERSION,
        "SecurityGroupId": security_group_id,
        "CidrIp": cidr,
        "Protocol": "tcp",
    }
    if action == "DescribeSecurityGroupAttributes":
        parameters["Direction"] = "ingress"
    else:
        parameters.update(
            {
                "Policy": "accept",
                "PortStart": "22",
                "PortEnd": "22",
                "Priority": "5",
                "Description": DESCRIPTION,
            }
        )
    return parameters


def api_request(
    parameters: dict[str, str],
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
) -> dict[str, object]:
    request = Request(
        f"https://{API_HOST}/?{canonical_query(parameters)}",
        headers=signed_headers(
            parameters,
            access_key,
            secret_key,
            service=API_SERVICE,
            region=API_REGION,
            session_token=session_token,
        ),
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS host
            raw = response.read(1_000_001)
    except HTTPError as error:
        try:
            payload = json.loads(error.read(1_000_001))
            metadata = payload.get("ResponseMetadata", {})
            api_error = metadata.get("Error", {}) if isinstance(metadata, dict) else {}
            code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
            code = "UNKNOWN"
        raise SecurityGroupError(f"VPC API rejected request ({code})") from error
    except URLError as error:
        raise SecurityGroupError("VPC API request failed") from error
    if len(raw) > 1_000_000:
        raise SecurityGroupError("VPC API response exceeded the safety limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SecurityGroupError("VPC API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise SecurityGroupError("VPC API response must be an object")
    metadata = payload.get("ResponseMetadata")
    if isinstance(metadata, dict) and metadata.get("Error"):
        api_error = metadata["Error"]
        code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        raise SecurityGroupError(f"VPC API rejected request ({code})")
    result = payload.get("Result")
    return result if isinstance(result, dict) else payload


def exact_rule_count(payload: dict[str, object], cidr: str) -> int:
    permissions = payload.get("Permissions", [])
    if not isinstance(permissions, list):
        raise SecurityGroupError("VPC API permissions are invalid")
    count = 0
    for rule in permissions:
        if not isinstance(rule, dict):
            continue
        try:
            ports = (int(rule.get("PortStart", -1)), int(rule.get("PortEnd", -1)))
            priority = int(rule.get("Priority", -1))
        except (TypeError, ValueError):
            continue
        if (
            rule.get("Direction") == "ingress"
            and rule.get("Policy") == "accept"
            and rule.get("Protocol") == "tcp"
            and ports == (22, 22)
            and priority == 5
            and rule.get("CidrIp") == cidr
            and rule.get("Description") == DESCRIPTION
            and rule.get("PrefixListId") in {None, ""}
            and rule.get("SourceGroupId") in {None, ""}
        ):
            count += 1
    return count


def wait_for_rule(
    security_group_id: str,
    cidr: str,
    expected: int,
    access_key: str,
    secret_key: str,
    session_token: str,
) -> None:
    parameters = rule_parameters(
        "DescribeSecurityGroupAttributes", security_group_id, cidr
    )
    for _ in range(20):
        payload = api_request(
            parameters,
            access_key,
            secret_key,
            session_token=session_token,
        )
        count = exact_rule_count(payload, cidr)
        if count == expected:
            return
        if count > 1:
            raise SecurityGroupError("more than one exact runner SSH rule exists")
        time.sleep(1)
    raise SecurityGroupError("runner SSH rule did not reach the expected state")


def change_rule(action: str, security_group_id: str, cidr: str) -> None:
    access_key = os.environ.get("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.environ.get("VOLCENGINE_SECRET_KEY", "")
    session_token = os.environ.get("VOLCENGINE_SESSION_TOKEN", "")
    if not access_key or not secret_key:
        raise SecurityGroupError("Volcengine workflow credentials are missing")

    describe = rule_parameters(
        "DescribeSecurityGroupAttributes", security_group_id, cidr
    )
    current = exact_rule_count(
        api_request(
            describe,
            access_key,
            secret_key,
            session_token=session_token,
        ),
        cidr,
    )
    if current > 1:
        raise SecurityGroupError("more than one exact runner SSH rule exists")
    if action == "close" and current == 0:
        print("WP08_SSH_INGRESS=CLOSED")
        return
    if action == "open" and current != 0:
        raise SecurityGroupError("runner SSH rule already exists before deployment")

    api_action = (
        "AuthorizeSecurityGroupIngress"
        if action == "open"
        else "RevokeSecurityGroupIngress"
    )
    api_request(
        rule_parameters(api_action, security_group_id, cidr),
        access_key,
        secret_key,
        session_token=session_token,
    )
    expected = 1 if action == "open" else 0
    wait_for_rule(
        security_group_id,
        cidr,
        expected,
        access_key,
        secret_key,
        session_token,
    )
    print(f"WP08_SSH_INGRESS={'OPEN' if action == 'open' else 'CLOSED'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("open", "close"))
    parser.add_argument("--security-group-id", required=True)
    parser.add_argument("--cidr", required=True)
    args = parser.parse_args()
    change_rule(args.action, args.security_group_id, args.cidr)


if __name__ == "__main__":
    try:
        main()
    except SecurityGroupError as error:
        print(f"WP08_SECURITY_GROUP_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
