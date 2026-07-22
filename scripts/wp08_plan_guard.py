#!/usr/bin/env python3
"""Reject destructive WP-08 Terraform plans without exposing plan values."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping


class PlanGuardError(RuntimeError):
    pass


SAFE_ACTIONS = {("no-op",), ("create",), ("read",), ("update",)}


def destructive_changes(plan: Mapping[str, object]) -> list[tuple[str, tuple[str, ...]]]:
    resource_changes = plan.get("resource_changes", [])
    if not isinstance(resource_changes, list):
        raise PlanGuardError("resource_changes must be a list")

    destructive: list[tuple[str, tuple[str, ...]]] = []
    for resource in resource_changes:
        if not isinstance(resource, Mapping):
            raise PlanGuardError("resource change must be an object")
        address = resource.get("address")
        change = resource.get("change")
        if not isinstance(address, str) or not address:
            raise PlanGuardError("resource change address is missing")
        if not isinstance(change, Mapping):
            raise PlanGuardError(f"resource change is missing for {address}")
        actions = change.get("actions")
        if not isinstance(actions, list) or not actions or not all(
            isinstance(action, str) for action in actions
        ):
            raise PlanGuardError(f"resource change actions are invalid for {address}")
        normalized = tuple(actions)
        if "delete" in normalized:
            destructive.append((address, normalized))
        elif normalized not in SAFE_ACTIONS:
            raise PlanGuardError(
                f"unsupported Terraform action sequence for {address}: {'/'.join(normalized)}"
            )
    return destructive


def validate_plan(plan: Mapping[str, object]) -> int:
    destructive = destructive_changes(plan)
    if destructive:
        summary = ", ".join(
            f"{address}={'/'.join(actions)}" for address, actions in destructive
        )
        raise PlanGuardError(f"destructive Terraform actions rejected: {summary}")
    resource_changes = plan.get("resource_changes", [])
    return len(resource_changes) if isinstance(resource_changes, list) else 0


def main() -> None:
    try:
        plan = json.load(sys.stdin)
        if not isinstance(plan, Mapping):
            raise PlanGuardError("Terraform plan JSON must be an object")
        count = validate_plan(plan)
    except (json.JSONDecodeError, PlanGuardError) as exc:
        print(f"WP08_TERRAFORM_PLAN_GUARD=FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        "WP08_TERRAFORM_PLAN_GUARD=PASS"
        f" resource_changes={count} destructive_changes=0"
    )


if __name__ == "__main__":
    main()
