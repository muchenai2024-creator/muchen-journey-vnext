import hashlib
import json

import pytest

from scripts import wp08_rds_network_audit as audit


def terraform_state():
    resources = []

    def add(resource_type, name, attributes):
        resources.append(
            {
                "mode": "managed",
                "type": resource_type,
                "name": name,
                "instances": [{"attributes": attributes}],
            }
        )

    add(
        "volcenginecc_ecs_instance",
        "app",
        {
            "primary_network_interface": {
                "primary_ip_address": "10.88.10.23",
                "subnet_id": "subnet-12345678",
                "vpc_id": "vpc-12345678",
            }
        },
    )
    add("volcenginecc_vpc_vpc", "staging", {"vpc_id": "vpc-12345678"})
    add(
        "volcenginecc_vpc_security_group",
        "app",
        {"security_group_id": "sg-12345678"},
    )
    add(
        "volcenginecc_rdspostgresql_allow_list",
        "app",
        {"allow_list_id": "acl-12345678"},
    )
    add(
        "volcenginecc_rdspostgresql_instance",
        "staging",
        {"instance_id": "postgres-12345678"},
    )
    return {"resources": resources}


def allowlist_detail(ip="10.88.10.23/32"):
    return {
        "AllowListId": "acl-12345678",
        "SecurityGroupBindInfos": [
            {
                "BindMode": "AssociateEcsIp",
                "SecurityGroupId": "sg-12345678",
                "IpList": [ip],
            }
        ],
        "AssociatedInstances": [
            {
                "InstanceId": "postgres-12345678",
                "VPC": "vpc-12345678",
                "IsLatest": True,
            }
        ],
    }


class _Response:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.raw


def test_frozen_state_and_live_allowlist_must_match_exactly():
    facts = audit.state_facts(terraform_state())
    audit.validate_detail(allowlist_detail(), facts)

    with pytest.raises(audit.NetworkAuditError, match="does not match"):
        audit.validate_detail(allowlist_detail("10.88.10.24/32"), facts)
    with pytest.raises(audit.NetworkAuditError, match="non-host network"):
        audit.validate_detail(allowlist_detail("10.88.10.0/24"), facts)

    stale = allowlist_detail()
    stale["AssociatedInstances"][0]["IsLatest"] = False
    with pytest.raises(audit.NetworkAuditError, match="not synchronized"):
        audit.validate_detail(stale, facts)


def test_state_parser_is_scoped_to_the_staging_primary_nic():
    state = terraform_state()
    ecs = state["resources"][0]["instances"][0]["attributes"]
    ecs["eip_address"] = {"ip_address": "8.8.8.8"}

    facts = audit.state_facts(state)

    assert {str(value) for value in facts.private_ips} == {"10.88.10.23"}


def test_rds_detail_request_is_signed_post_with_body_hash(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({"Result": allowlist_detail()})

    monkeypatch.setattr(audit, "urlopen", fake_urlopen)

    result = audit.request_detail("acl-12345678", "access-key", "secret-key")

    request = captured["request"]
    assert result["AllowListId"] == "acl-12345678"
    assert request.get_method() == "POST"
    assert request.full_url.startswith(f"https://{audit.API_HOST}/?")
    assert request.headers["X-content-sha256"] == hashlib.sha256(request.data).hexdigest()
    assert captured["timeout"] == 20


def test_audit_output_is_identifier_and_ip_free(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(terraform_state()))
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "access-key")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "secret-key")
    monkeypatch.setattr(audit, "request_detail", lambda *_args, **_kwargs: allowlist_detail())

    audit.audit(state_path)

    output = capsys.readouterr().out
    assert output.strip() == (
        "WP08_RDS_NETWORK_AUDIT=PASS ecs_private_ip_count=1 "
        "allowlist_match=true instance_association=true "
        "vpc_match=true allowlist_latest=true"
    )
    assert "10.88" not in output
    assert "acl-" not in output
