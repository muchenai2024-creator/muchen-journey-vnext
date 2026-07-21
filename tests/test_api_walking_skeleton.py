from fastapi.testclient import TestClient

from journey_api.fixtures import ASSIGNMENT_ID
from journey_api.main import app

client = TestClient(app, base_url="http://localhost")
learner_headers = {"X-Fixture-Role": "LEARNER"}
reviewer_headers = {"X-Fixture-Role": "REVIEWER"}


def assert_ok(response):
    assert response.status_code < 400, response.text
    assert response.headers["X-Request-ID"].startswith("req_")
    return response.json()["data"]


def test_standard_walking_skeleton_and_idempotency():
    assert client.get("/api/v1/reviews", headers=learner_headers).status_code == 403
    assert client.get("/api/v1/me/current-action", headers=reviewer_headers).status_code == 403

    current = assert_ok(client.get("/api/v1/me/current-action", headers=learner_headers))
    assert current["action_type"] == "START_OR_CONTINUE_TASK"
    assert current["allowed_commands"] == ["start"]

    detail_before = assert_ok(
        client.get(f"/api/v1/me/assignments/{ASSIGNMENT_ID}", headers=learner_headers)
    )
    detail_after = assert_ok(
        client.get(f"/api/v1/me/assignments/{ASSIGNMENT_ID}", headers=learner_headers)
    )
    assert detail_before == detail_after

    start_payload = {"expected_revision": current["revision"]}
    start_headers = {**learner_headers, "Idempotency-Key": "test-start-0001"}
    conflict = client.post(
        f"/api/v1/me/assignments/{ASSIGNMENT_ID}/start",
        headers={**learner_headers, "Idempotency-Key": "test-start-conflict"},
        json={"expected_revision": current["revision"] + 1},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"
    started = assert_ok(
        client.post(
            f"/api/v1/me/assignments/{ASSIGNMENT_ID}/start",
            headers=start_headers,
            json=start_payload,
        )
    )
    replay = assert_ok(
        client.post(
            f"/api/v1/me/assignments/{ASSIGNMENT_ID}/start",
            headers=start_headers,
            json=start_payload,
        )
    )
    assert started["status"] == "IN_PROGRESS"
    assert replay["resource_id"] == started["resource_id"]
    assert replay["idempotency_replay"] is True
    reused = client.post(
        f"/api/v1/me/assignments/{ASSIGNMENT_ID}/start",
        headers=start_headers,
        json={"expected_revision": started["revision"]},
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    submission_body = (
        "问题：新人无法确认当前唯一行动。事实一：入口存在重复说明。"
        "事实二：主管反馈责任人不清。行动：统一入口、明确责任人、用理解率验证；"
        "两周内当前行动理解率低于 90% 时停止扩量并修订说明。"
    )
    submitted = assert_ok(
        client.post(
            f"/api/v1/me/assignments/{ASSIGNMENT_ID}/submissions",
            headers={**learner_headers, "Idempotency-Key": "test-submit-0001"},
            json={"expected_revision": started["revision"], "body": submission_body},
        )
    )
    assert submitted["assignment_status"] == "SUBMITTED"
    assert submitted["version_no"] == 1
    assert submitted["submission_id"]

    queue = assert_ok(client.get("/api/v1/reviews", headers=reviewer_headers))
    assert len(queue["items"]) == 1
    review = queue["items"][0]

    review_detail_before = assert_ok(
        client.get(f"/api/v1/reviews/{review['id']}", headers=reviewer_headers)
    )
    review_detail_after = assert_ok(
        client.get(f"/api/v1/reviews/{review['id']}", headers=reviewer_headers)
    )
    assert review_detail_before == review_detail_after
    assert review_detail_before["submission_body"] == submission_body

    started_review = assert_ok(
        client.post(
            f"/api/v1/reviews/{review['id']}/start",
            headers={**reviewer_headers, "Idempotency-Key": "test-review-start-0001"},
            json={"expected_revision": review["revision"]},
        )
    )
    assert started_review["review_status"] == "IN_REVIEW"

    invalid_rubric = client.post(
        f"/api/v1/reviews/{review['id']}/finalize",
        headers={**reviewer_headers, "Idempotency-Key": "test-review-invalid"},
        json={
            "expected_revision": started_review["review_revision"],
            "overall_decision": "APPROVE",
            "overall_feedback": "仍有一个维度未达标，不能通过。",
            "rubric_evaluations": [
                {"dimension_key": key, "rating": rating, "feedback": "逐维反馈清楚可行动。"}
                for key, rating in {
                    "problem_clarity": "MEETS",
                    "evidence_quality": "NEEDS_WORK",
                    "action_feasibility": "MEETS",
                    "validation_design": "MEETS",
                }.items()
            ],
        },
    )
    assert invalid_rubric.status_code == 422
    assert invalid_rubric.json()["error"]["code"] == "VALIDATION_FAILED"

    finalized = assert_ok(
        client.post(
            f"/api/v1/reviews/{review['id']}/finalize",
            headers={**reviewer_headers, "Idempotency-Key": "test-review-final-0001"},
            json={
                "expected_revision": started_review["review_revision"],
                "overall_decision": "APPROVE",
                "overall_feedback": "问题、依据、行动与验证护栏完整，可以进入交接。",
                "rubric_evaluations": [
                    {
                        "dimension_key": key,
                        "rating": "MEETS",
                        "feedback": "证据符合该维度的批准锚点。",
                    }
                    for key in (
                        "problem_clarity",
                        "evidence_quality",
                        "action_feasibility",
                        "validation_design",
                    )
                ],
            },
        )
    )
    assert finalized["review_status"] == "FINALIZED"

    result = assert_ok(client.get("/api/v1/me/result", headers=learner_headers))
    assert result["status"] == "HANDOFF_READY"
    assert result["decision"] == "PASS"

    completed = assert_ok(client.get("/api/v1/me/current-action", headers=learner_headers))
    assert completed["action_type"] == "VIEW_RESULT_OR_HANDOFF"


def test_fixture_identity_fails_closed_without_header():
    response = client.get("/api/v1/me/current-action")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_untrusted_request_id_is_replaced():
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "contains spaces and is not trusted"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")
