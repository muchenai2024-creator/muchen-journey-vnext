#!/usr/bin/env python3
"""Find one exact existing WP-08 DNS record without disclosing its identity."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_HOST = "open.volcengineapi.com"
API_REGION = "cn-north-1"
API_SERVICE = "dns"
API_VERSION = "2018-08-01"
PROJECT_NAME = "journey-next-staging"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
RECORD_ID = re.compile(r"^[^|\s]{1,160}$")


class DNSRecordError(RuntimeError):
    pass


def canonical_query(parameters: dict[str, str]) -> str:
    return "&".join(
        f"{quote(key, safe='-_.~')}={quote(str(parameters[key]), safe='-_.~')}"
        for key in sorted(parameters)
    )


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def signed_headers(
    parameters: dict[str, str],
    access_key: str,
    secret_key: str,
    *,
    service: str = API_SERVICE,
    region: str = API_REGION,
    now: datetime | None = None,
    session_token: str = "",
) -> dict[str, str]:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    date = timestamp[:8]
    headers = {
        "Host": API_HOST,
        "X-Content-Sha256": EMPTY_SHA256,
        "X-Date": timestamp,
    }
    if session_token:
        headers["X-Security-Token"] = session_token
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    names = sorted(normalized_headers)
    canonical_headers = "".join(
        f"{name}:{normalized_headers[name]}\n" for name in names
    )
    signed_names = ";".join(names)
    canonical_request = "\n".join(
        (
            "GET",
            "/",
            canonical_query(parameters),
            canonical_headers,
            signed_names,
            EMPTY_SHA256,
        )
    )
    scope = f"{date}/{region}/{service}/request"
    string_to_sign = "\n".join(
        (
            "HMAC-SHA256",
            timestamp,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        )
    )
    signing_key = _hmac(
        _hmac(_hmac(_hmac(secret_key.encode(), date), region), service), "request"
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode(), hashlib.sha256
    ).hexdigest()
    headers["Authorization"] = (
        f"HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_names}, Signature={signature}"
    )
    return headers


def fetch_records(
    zone_id: str,
    access_key: str,
    secret_key: str,
    *,
    session_token: str = "",
) -> dict[str, object]:
    parameters = {
        "Action": "ListRecords",
        "PageNumber": "1",
        "PageSize": "100",
        "ProjectName": PROJECT_NAME,
        "Version": API_VERSION,
        "ZID": zone_id,
    }
    raw = b""
    for attempt in range(1, 4):
        request = Request(
            f"https://{API_HOST}/?{canonical_query(parameters)}",
            headers=signed_headers(
                parameters,
                access_key,
                secret_key,
                session_token=session_token,
            ),
            method="GET",
        )
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS host
                raw = response.read(1_000_001)
            break
        except HTTPError as error:
            if attempt == 3 or (error.code != 429 and error.code < 500):
                raise DNSRecordError(f"DNS API returned HTTP {error.code}") from error
        except URLError as error:
            if attempt == 3:
                raise DNSRecordError("DNS API request failed") from error
        time.sleep(attempt)
    if len(raw) > 1_000_000:
        raise DNSRecordError("DNS API response exceeded the safety limit")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DNSRecordError("DNS API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise DNSRecordError("DNS API response must be an object")
    metadata = payload.get("ResponseMetadata")
    if isinstance(metadata, dict) and metadata.get("Error"):
        api_error = metadata["Error"]
        code = api_error.get("Code", "UNKNOWN") if isinstance(api_error, dict) else "UNKNOWN"
        raise DNSRecordError(f"DNS API rejected ListRecords ({code})")
    result = payload.get("Result")
    if not isinstance(result, dict):
        raise DNSRecordError("DNS API result is missing")
    return result


def record_candidates(
    value: object, inherited: dict[str, object] | None = None
) -> Iterator[dict[str, object]]:
    context = dict(inherited or {})
    if isinstance(value, dict):
        for key in ("Host", "Type", "Line", "TTL", "Value", "Enable", "Remark"):
            if key in value:
                context[key] = value[key]
        if "RecordID" in value:
            yield {**context, "RecordID": value["RecordID"]}
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from record_candidates(child, context)
    elif isinstance(value, list):
        for child in value:
            yield from record_candidates(child, context)


def _enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return str(value).lower() in {"true", "1", "open", "enabled"}


def exact_record_id(result: dict[str, object], expected_value: str) -> str:
    matches = []
    for record in record_candidates(result):
        line = str(record.get("Line", "")).split(";", 1)[0]
        try:
            ttl = int(record.get("TTL", -1))
        except (TypeError, ValueError):
            ttl = -1
        if (
            record.get("Host") == "@"
            and record.get("Type") == "A"
            and line == "default"
            and record.get("Value") == expected_value
            and ttl == 600
            and _enabled(record.get("Enable"))
            and record.get("Remark") == "vNext staging"
        ):
            matches.append(str(record.get("RecordID", "")))
    if len(matches) != 1:
        raise DNSRecordError(
            f"expected exactly one matching staging DNS record, found {len(matches)}"
        )
    if not RECORD_ID.fullmatch(matches[0]):
        raise DNSRecordError("matching DNS record has an unsafe identifier")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone-id", required=True)
    parser.add_argument("--expected-value", required=True)
    args = parser.parse_args()
    access_key = os.environ.get("VOLCENGINE_ACCESS_KEY", "")
    secret_key = os.environ.get("VOLCENGINE_SECRET_KEY", "")
    if not access_key or not secret_key:
        raise DNSRecordError("Volcengine workflow credentials are missing")
    if not re.fullmatch(r"[0-9]{1,32}", args.zone_id):
        raise DNSRecordError("DNS zone identifier is invalid")
    try:
        ipaddress.IPv4Address(args.expected_value)
    except ipaddress.AddressValueError as error:
        raise DNSRecordError("expected DNS value must be one IPv4 address") from error
    result = fetch_records(
        args.zone_id,
        access_key,
        secret_key,
        session_token=os.environ.get("VOLCENGINE_SESSION_TOKEN", ""),
    )
    print(exact_record_id(result, args.expected_value))


if __name__ == "__main__":
    try:
        main()
    except DNSRecordError as error:
        print(f"WP08_DNS_RECONCILIATION_ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
