import pytest

from scripts import wp08_security_group as security_group


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
