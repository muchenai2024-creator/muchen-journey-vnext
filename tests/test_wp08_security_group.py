import json

import pytest

from scripts import wp08_security_group as security_group


class _Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self._raw


def test_rule_parameters_never_include_unused_source_selectors():
    parameters = security_group.rule_parameters(
        "AuthorizeSecurityGroupIngress",
        "sg-12345678",
        "8.8.8.8/32",
    )

    assert parameters["CidrIp"] == "8.8.8.8/32"
    assert parameters["PortStart"] == "22"
    assert parameters["PortEnd"] == "22"
    assert "PrefixListId" not in parameters
    assert "SourceGroupId" not in parameters


def test_runner_rule_requires_one_public_ipv4_host():
    with pytest.raises(security_group.SecurityGroupError, match="public IPv4 /32"):
        security_group.rule_parameters(
            "AuthorizeSecurityGroupIngress",
            "sg-12345678",
            "127.0.0.1/32",
        )
    with pytest.raises(security_group.SecurityGroupError, match="public IPv4 /32"):
        security_group.rule_parameters(
            "AuthorizeSecurityGroupIngress",
            "sg-12345678",
            "192.0.2.0/24",
        )


def test_exact_rule_match_rejects_empty_prefix_list_side_effects():
    cidr = "192.0.2.10/32"
    exact = {
        "Direction": "ingress",
        "Policy": "accept",
        "Protocol": "tcp",
        "PortStart": 22,
        "PortEnd": 22,
        "Priority": 5,
        "CidrIp": cidr,
        "Description": security_group.DESCRIPTION,
    }
    payload = {
        "Permissions": [
            exact,
            {**exact, "PrefixListId": "list-unexpected"},
        ]
    }

    assert security_group.exact_rule_count(payload, cidr) == 1


def test_sanitized_live_no_match_response_treats_null_permissions_as_empty(
    monkeypatch,
):
    cidr = "8.8.8.10/32"
    response = {
        "ResponseMetadata": {
            "RequestId": "redacted",
            "Action": "DescribeSecurityGroupAttributes",
            "Version": security_group.API_VERSION,
            "Service": security_group.API_SERVICE,
            "Region": security_group.API_REGION,
        },
        "Result": {
            "RequestId": "redacted",
            "SecurityGroupId": "sg-redacted",
            "Permissions": None,
        },
    }
    monkeypatch.setattr(
        security_group,
        "urlopen",
        lambda *_args, **_kwargs: _Response(response),
    )

    result = security_group.api_request(
        security_group.rule_parameters(
            "DescribeSecurityGroupAttributes",
            "sg-12345678",
            cidr,
        ),
        "access-key",
        "secret-key",
    )

    assert security_group.exact_rule_count(result, cidr) == 0


def test_open_continues_from_the_live_null_no_match_shape(monkeypatch, capsys):
    cidr = "8.8.8.10/32"
    exact = {
        "Direction": "ingress",
        "Policy": "accept",
        "Protocol": "tcp",
        "PortStart": 22,
        "PortEnd": 22,
        "Priority": 5,
        "CidrIp": cidr,
        "Description": security_group.DESCRIPTION,
    }
    responses = iter(
        (
            {"Permissions": None},
            {},
            {"Permissions": [exact]},
        )
    )
    actions = []

    def fake_api_request(parameters, *_args, **_kwargs):
        actions.append(parameters["Action"])
        return next(responses)

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "access-key")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "secret-key")
    monkeypatch.setattr(security_group, "api_request", fake_api_request)

    security_group.change_rule("open", "sg-12345678", cidr)

    assert actions == [
        "DescribeSecurityGroupAttributes",
        "AuthorizeSecurityGroupIngress",
        "DescribeSecurityGroupAttributes",
    ]
    assert capsys.readouterr().out.strip() == "WP08_SSH_INGRESS=OPEN"


def test_permissions_with_an_unexpected_shape_still_fail_closed():
    with pytest.raises(
        security_group.SecurityGroupError,
        match="permissions are invalid",
    ):
        security_group.exact_rule_count(
            {"Permissions": {"Permission": []}},
            "192.0.2.10/32",
        )
