from datetime import datetime, timezone

import pytest

from scripts import wp08_dns_record as dns


def test_signer_matches_official_volcengine_sdk_vector():
    headers = dns.signed_headers(
        {
            "Action": "ListUsers",
            "Limit": "5",
            "Offset": "0",
            "Version": "2018-01-01",
        },
        "ak",
        "sk",
        service="iam",
        region="cn-north-1",
        now=datetime(2021, 12, 28, 17, 23, 26, tzinfo=timezone.utc),
    )

    assert headers["X-Content-Sha256"] == dns.EMPTY_SHA256
    assert headers["Authorization"].endswith(
        "Signature=4f5b9d2b436092f11a41b5ad0d6eb6a868b30bd3955f480fa1d6bf1ed3073eba"
    )


def test_exact_record_requires_all_reviewed_attributes_and_one_match():
    expected = "192.0.2.10"
    result = {
        "RecordSets": [
            {
                "Host": "@",
                "Type": "A",
                "Line": "default;0.0.0.0/0",
                "TTL": 600,
                "Records": [
                    {
                        "RecordID": "record-123",
                        "Value": expected,
                        "Enable": True,
                        "Remark": "vNext staging",
                    }
                ],
            }
        ]
    }

    assert dns.exact_record_id(result, expected) == "record-123"

    duplicate = {"RecordSets": result["RecordSets"] * 2}
    with pytest.raises(dns.DNSRecordError, match="found 2"):
        dns.exact_record_id(duplicate, expected)

    result["RecordSets"][0]["TTL"] = 300
    with pytest.raises(dns.DNSRecordError, match="found 0"):
        dns.exact_record_id(result, expected)


def test_record_identifier_cannot_escape_terraform_import_identity():
    result = {
        "Records": [
            {
                "RecordID": "unsafe|identity",
                "Host": "@",
                "Type": "A",
                "Line": "default",
                "TTL": "600",
                "Value": "192.0.2.10",
                "Enable": 1,
                "Remark": "vNext staging",
            }
        ]
    }

    with pytest.raises(dns.DNSRecordError, match="unsafe identifier"):
        dns.exact_record_id(result, "192.0.2.10")
