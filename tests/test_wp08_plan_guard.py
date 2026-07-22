import json

import pytest

import scripts.wp08_plan_guard as guard


def change(address: str, actions: list[str], *, before=None, after=None) -> dict:
    return {
        "address": address,
        "change": {"actions": actions, "before": before, "after": after},
    }


def test_accepts_non_destructive_plan():
    plan = {
        "resource_changes": [
            change("test.noop", ["no-op"]),
            change("test.create", ["create"]),
            change("test.update", ["update"]),
            change("data.test.read", ["read"]),
        ]
    }
    assert guard.validate_plan(plan) == 4


@pytest.mark.parametrize(
    "actions",
    (["delete"], ["delete", "create"], ["create", "delete"]),
)
def test_rejects_destroy_and_both_replacement_orders(actions: list[str]):
    plan = {"resource_changes": [change("volcenginecc_ecs_instance.app", actions)]}
    with pytest.raises(guard.PlanGuardError, match="destructive Terraform actions rejected"):
        guard.validate_plan(plan)


def test_rejects_unknown_action_sequence_fail_closed():
    plan = {"resource_changes": [change("test.future", ["future-action"])]}
    with pytest.raises(guard.PlanGuardError, match="unsupported Terraform action sequence"):
        guard.validate_plan(plan)


def test_cli_failure_does_not_echo_plan_values(monkeypatch, capsys):
    secret = "must-not-appear"
    plan = {
        "resource_changes": [
            change(
                "volcenginecc_ecs_instance.app",
                ["delete", "create"],
                before={"password": secret},
                after={"password": secret},
            )
        ]
    }
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(json.dumps(plan)))
    with pytest.raises(SystemExit) as exc:
        guard.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "volcenginecc_ecs_instance.app" in captured.err
    assert secret not in captured.err
