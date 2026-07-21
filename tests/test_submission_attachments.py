import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from journey_api.db import SessionLocal
from journey_api.fixtures import REVIEWER_ID, TASK_VERSION_V2_ID
from journey_api.main import app
from journey_api.models import (
    Attachment,
    AttachmentScanStatus,
    AttachmentStatus,
    Review,
    Submission,
    SubmissionDraft,
    SubmissionVersion,
    SubmissionVersionAttachment,
)


operator_headers = {"X-Fixture-Role": "OPERATOR"}
reviewer_headers = {"X-Fixture-Role": "REVIEWER"}


def client_for(label: str) -> TestClient:
    return TestClient(app, base_url="http://localhost", client=(label, 51_000))


def assert_ok(response):
    assert response.status_code < 400, response.text
    assert response.headers["X-Request-ID"].startswith("req_")
    return response.json()["data"]


def new_attachment_learner(label: str):
    created = assert_ok(
        client_for(f"operator-{label}").post(
            "/api/v1/ops/invites",
            headers={
                **operator_headers,
                "Idempotency-Key": f"wp03-invite-{uuid.uuid4()}",
            },
            json={
                "purpose": "验证 WP-03 提交、附件与修订路径",
                "expires_in_hours": 24,
                "role": "LEARNER",
                "reviewer_id": str(REVIEWER_ID),
                "task_version_id": str(TASK_VERSION_V2_ID),
                "target_user_id": None,
            },
        )
    )
    learner = client_for(label)
    exchanged = assert_ok(
        learner.post(
            "/api/v1/join/exchange",
            json={"token": created["invite_token"], "return_to": "/app"},
        )
    )
    confirmed = assert_ok(
        learner.post(
            "/api/v1/identity/confirm",
            headers={"X-CSRF-Token": exchanged["csrf_token"]},
            json={
                "display_name": f"WP03 新人 {label}",
                "accepted_purpose": True,
                "return_to": "/app",
            },
        )
    )
    current = assert_ok(learner.get("/api/v1/me/current-action"))
    started = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{current['resource_id']}/start",
            headers={
                "Idempotency-Key": f"wp03-start-{uuid.uuid4()}",
                "X-CSRF-Token": confirmed["csrf_token"],
            },
            json={"expected_revision": current["revision"]},
        )
    )
    return learner, confirmed["csrf_token"], current["resource_id"], started


def upload_attachment(
    learner: TestClient,
    csrf_token: str,
    assignment_id: str,
    *,
    filename: str,
    content_type: str,
    content: bytes,
):
    digest = hashlib.sha256(content).hexdigest()
    key = f"wp03-presign-{uuid.uuid4()}"
    payload = {
        "assignment_id": assignment_id,
        "purpose": "SUBMISSION_EVIDENCE",
        "original_filename": filename,
        "content_type": content_type,
        "size_bytes": len(content),
        "sha256": digest,
    }
    presigned = assert_ok(
        learner.post(
            "/api/v1/attachments/presign",
            headers={"Idempotency-Key": key, "X-CSRF-Token": csrf_token},
            json=payload,
        )
    )
    replay = assert_ok(
        learner.post(
            "/api/v1/attachments/presign",
            headers={"Idempotency-Key": key, "X-CSRF-Token": csrf_token},
            json=payload,
        )
    )
    assert replay["id"] == presigned["id"]
    assert replay["idempotency_replay"] is True
    uploaded = assert_ok(
        learner.put(
            presigned["upload_url"],
            headers={"Content-Type": content_type, "X-CSRF-Token": csrf_token},
            content=content,
        )
    )
    assert uploaded["status"] == "UPLOADED"
    completed = assert_ok(
        learner.post(
            f"/api/v1/attachments/{presigned['id']}/complete",
            headers={
                "Idempotency-Key": f"wp03-complete-{uuid.uuid4()}",
                "X-CSRF-Token": csrf_token,
            },
            json={
                "size_bytes": len(content),
                "content_type": content_type,
                "sha256": digest,
            },
        )
    )
    return completed


def submission_body(label: str) -> str:
    return (
        f"问题：{label} 当前提交恢复路径不清。事实一：重复点击可能发生；"
        "事实二：网络响应可能丢失。行动：保存草稿、复用幂等键、显示固定版本；"
        "两周内重复事实不为零时停止扩量并修复。"
    )


def test_attachment_scope_type_size_filename_scan_and_download_isolation():
    learner_a, csrf_a, assignment_a, started_a = new_attachment_learner("attachment-a")
    learner_b, csrf_b, assignment_b, started_b = new_attachment_learner("attachment-b")

    invalid_name = learner_a.post(
        "/api/v1/attachments/presign",
        headers={"Idempotency-Key": f"bad-name-{uuid.uuid4()}", "X-CSRF-Token": csrf_a},
        json={
            "assignment_id": assignment_a,
            "purpose": "SUBMISSION_EVIDENCE",
            "original_filename": "../越界.pdf",
            "content_type": "application/pdf",
            "size_bytes": 20,
            "sha256": "a" * 64,
        },
    )
    assert invalid_name.status_code == 422
    assert invalid_name.json()["error"]["code"] == "VALIDATION_FAILED"

    too_large = learner_a.post(
        "/api/v1/attachments/presign",
        headers={"Idempotency-Key": f"too-large-{uuid.uuid4()}", "X-CSRF-Token": csrf_a},
        json={
            "assignment_id": assignment_a,
            "purpose": "SUBMISSION_EVIDENCE",
            "original_filename": "large.pdf",
            "content_type": "application/pdf",
            "size_bytes": 5 * 1024 * 1024 + 1,
            "sha256": "a" * 64,
        },
    )
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "ATTACHMENT_TOO_LARGE"

    mismatch = b"this is not a PDF"
    mismatch_digest = hashlib.sha256(mismatch).hexdigest()
    mismatch_intent = assert_ok(
        learner_a.post(
            "/api/v1/attachments/presign",
            headers={"Idempotency-Key": f"mismatch-{uuid.uuid4()}", "X-CSRF-Token": csrf_a},
            json={
                "assignment_id": assignment_a,
                "purpose": "SUBMISSION_EVIDENCE",
                "original_filename": "mismatch.pdf",
                "content_type": "application/pdf",
                "size_bytes": len(mismatch),
                "sha256": mismatch_digest,
            },
        )
    )
    mismatch_upload = learner_a.put(
        mismatch_intent["upload_url"],
        headers={"Content-Type": "application/pdf", "X-CSRF-Token": csrf_a},
        content=mismatch,
    )
    assert mismatch_upload.status_code == 422

    rejected_content = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE local contract sample"
    rejected_digest = hashlib.sha256(rejected_content).hexdigest()
    rejected = assert_ok(
        learner_a.post(
            "/api/v1/attachments/presign",
            headers={"Idempotency-Key": f"rejected-{uuid.uuid4()}", "X-CSRF-Token": csrf_a},
            json={
                "assignment_id": assignment_a,
                "purpose": "SUBMISSION_EVIDENCE",
                "original_filename": "local-scan.txt",
                "content_type": "text/plain",
                "size_bytes": len(rejected_content),
                "sha256": rejected_digest,
            },
        )
    )
    assert_ok(
        learner_a.put(
            rejected["upload_url"],
            headers={"Content-Type": "text/plain", "X-CSRF-Token": csrf_a},
            content=rejected_content,
        )
    )
    scan_rejected = learner_a.post(
        f"/api/v1/attachments/{rejected['id']}/complete",
        headers={"Idempotency-Key": f"scan-{uuid.uuid4()}", "X-CSRF-Token": csrf_a},
        json={
            "size_bytes": len(rejected_content),
            "content_type": "text/plain",
            "sha256": rejected_digest,
        },
    )
    assert scan_rejected.status_code == 422
    with SessionLocal() as session:
        stored_rejected = session.get(Attachment, uuid.UUID(rejected["id"]))
        assert stored_rejected is not None
        assert stored_rejected.status == AttachmentStatus.REJECTED
        assert stored_rejected.scan_status == AttachmentScanStatus.LOCAL_REJECTED

    ready = upload_attachment(
        learner_a,
        csrf_a,
        assignment_a,
        filename="依据.txt",
        content_type="text/plain",
        content="两条可核对的观察。".encode(),
    )
    assert ready["status"] == "READY"
    assert learner_b.get(f"/api/v1/attachments/{ready['id']}/download").status_code == 404
    cross_object = learner_b.post(
        f"/api/v1/me/assignments/{assignment_b}/submissions",
        headers={"Idempotency-Key": f"cross-{uuid.uuid4()}", "X-CSRF-Token": csrf_b},
        json={
            "expected_revision": started_b["revision"],
            "body": submission_body("跨对象附件"),
            "attachment_ids": [ready["id"]],
        },
    )
    assert cross_object.status_code == 422
    assert cross_object.json()["error"]["code"] == "VALIDATION_FAILED"

    submitted_b = assert_ok(
        learner_b.post(
            f"/api/v1/me/assignments/{assignment_b}/submissions",
            headers={
                "Idempotency-Key": f"scoped-link-{uuid.uuid4()}",
                "X-CSRF-Token": csrf_b,
            },
            json={
                "expected_revision": started_b["revision"],
                "body": submission_body("数据库附件对象隔离"),
                "attachment_ids": [],
            },
        )
    )
    try:
        with SessionLocal.begin() as session:
            submission_b = session.get(Submission, uuid.UUID(submitted_b["submission_id"]))
            assert submission_b is not None
            session.add(
                SubmissionVersionAttachment(
                    submission_id=submission_b.id,
                    submission_version_id=uuid.UUID(
                        submitted_b["submission_version_id"]
                    ),
                    attachment_id=uuid.UUID(ready["id"]),
                    organization_id=submission_b.organization_id,
                    assignment_id=submission_b.assignment_id,
                    position=1,
                )
            )
            session.flush()
    except DBAPIError as error:
        assert "foreign key" in str(error).lower()
    else:
        raise AssertionError("cross-assignment attachment link unexpectedly succeeded")

    deleted = assert_ok(
        learner_a.delete(
            f"/api/v1/attachments/{ready['id']}", headers={"X-CSRF-Token": csrf_a}
        )
    )
    assert deleted["status"] == "DELETED"
    assert learner_a.get(f"/api/v1/attachments/{ready['id']}/download").status_code == 404
    assert started_a["status"] == "IN_PROGRESS"


def test_draft_first_submit_revision_history_and_database_immutability():
    learner, csrf_token, assignment_id, started = new_attachment_learner("history")
    attachment = upload_attachment(
        learner,
        csrf_token,
        assignment_id,
        filename="首版依据.txt",
        content_type="text/plain",
        content="首版事实一与事实二。".encode(),
    )
    first_body = submission_body("首版")
    draft_payload = {
        "expected_revision": started["revision"],
        "body": first_body,
        "attachment_ids": [attachment["id"]],
    }
    draft_key = f"draft-{uuid.uuid4()}"
    draft = assert_ok(
        learner.put(
            f"/api/v1/me/assignments/{assignment_id}/draft",
            headers={"Idempotency-Key": draft_key, "X-CSRF-Token": csrf_token},
            json=draft_payload,
        )
    )
    draft_replay = assert_ok(
        learner.put(
            f"/api/v1/me/assignments/{assignment_id}/draft",
            headers={"Idempotency-Key": draft_key, "X-CSRF-Token": csrf_token},
            json=draft_payload,
        )
    )
    assert draft_replay["body"] == draft["body"]
    assert draft_replay["revision"] == draft["revision"]
    assert draft_replay["idempotency_replay"] is True
    refreshed = assert_ok(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
    assert refreshed["draft"]["body"] == first_body
    assert refreshed["draft"]["attachment_ids"] == [attachment["id"]]
    assert refreshed["allowed_commands"] == ["submit"]

    submit_key = f"submit-{uuid.uuid4()}"
    submit_payload = {
        "expected_revision": started["revision"],
        "body": first_body,
        "attachment_ids": [attachment["id"]],
    }
    first = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            headers={"Idempotency-Key": submit_key, "X-CSRF-Token": csrf_token},
            json=submit_payload,
        )
    )
    replay = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            headers={"Idempotency-Key": submit_key, "X-CSRF-Token": csrf_token},
            json=submit_payload,
        )
    )
    assert first["version_no"] == 1
    assert replay["submission_version_id"] == first["submission_version_id"]
    assert replay["idempotency_replay"] is True
    reused = learner.post(
        f"/api/v1/me/assignments/{assignment_id}/submissions",
        headers={"Idempotency-Key": submit_key, "X-CSRF-Token": csrf_token},
        json={**submit_payload, "body": submission_body("不同正文")},
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    after_submit = assert_ok(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
    assert after_submit["draft"] is None
    assert after_submit["submission"]["current_version_no"] == 1
    assert after_submit["submission"]["versions"][0]["body"] == first_body
    history = assert_ok(learner.get(f"/api/v1/me/submissions/{first['submission_id']}"))
    assert history == after_submit["submission"]
    reviewer_download = client_for("reviewer-download").get(
        f"/api/v1/attachments/{attachment['id']}/download", headers=reviewer_headers
    )
    assert reviewer_download.status_code == 200
    assert reviewer_download.headers["Content-Disposition"].startswith("attachment;")
    bound_delete = learner.delete(
        f"/api/v1/attachments/{attachment['id']}", headers={"X-CSRF-Token": csrf_token}
    )
    assert bound_delete.status_code == 409

    with SessionLocal() as session:
        review = session.scalar(
            select(Review).where(
                Review.submission_version_id == uuid.UUID(first["submission_version_id"])
            )
        )
        assert review is not None
        review_id = review.id
        review_revision = review.revision
    reviewer = client_for("revision-reviewer")
    review_started = assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{review_id}/start",
            headers={**reviewer_headers, "Idempotency-Key": f"review-start-{uuid.uuid4()}"},
            json={"expected_revision": review_revision},
        )
    )
    feedback = "请补充附件依据的来源，并把第一步责任人写得更具体。"
    assert_ok(
        reviewer.post(
            f"/api/v1/reviews/{review_id}/finalize",
            headers={**reviewer_headers, "Idempotency-Key": f"review-final-{uuid.uuid4()}"},
            json={
                "expected_revision": review_started["review_revision"],
                "overall_decision": "REQUEST_REVISION",
                "overall_feedback": feedback,
                "rubric_evaluations": [
                    {"dimension_key": key, "rating": rating, "feedback": note}
                    for key, rating, note in (
                        ("problem_clarity", "MEETS", "问题对象和边界已经表达清楚。"),
                        ("evidence_quality", "NEEDS_WORK", "请补充附件依据的来源。"),
                        ("action_feasibility", "MEETS", "行动步骤数量符合要求。"),
                        ("validation_design", "MEETS", "验证指标和停止条件可观察。"),
                    )
                ],
            },
        )
    )
    revision_detail = assert_ok(learner.get(f"/api/v1/me/assignments/{assignment_id}"))
    assert revision_detail["allowed_commands"] == ["submit_revision"]
    assert revision_detail["latest_revision_feedback"] == feedback
    assert revision_detail["submission"]["versions"][0]["body"] == first_body

    revised_body = submission_body("修订版") + " 已补充来源和明确责任人。"
    saved_revision_draft = assert_ok(
        learner.put(
            f"/api/v1/me/assignments/{assignment_id}/draft",
            headers={"Idempotency-Key": f"revision-draft-{uuid.uuid4()}", "X-CSRF-Token": csrf_token},
            json={
                "expected_revision": revision_detail["revision"],
                "body": revised_body,
                "attachment_ids": [],
            },
        )
    )
    assert saved_revision_draft["body"] == revised_body
    second = assert_ok(
        learner.post(
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            headers={"Idempotency-Key": f"revision-submit-{uuid.uuid4()}", "X-CSRF-Token": csrf_token},
            json={
                "expected_revision": revision_detail["revision"],
                "body": revised_body,
                "attachment_ids": [],
            },
        )
    )
    assert second["submission_id"] == first["submission_id"]
    assert second["version_no"] == 2
    final_history = assert_ok(learner.get(f"/api/v1/me/submissions/{first['submission_id']}"))
    assert [item["body"] for item in final_history["versions"]] == [first_body, revised_body]
    assert final_history["versions"][0]["decision"] == "REVISION_REQUIRED"
    assert final_history["versions"][0]["feedback"] == feedback

    first_version_id = uuid.UUID(first["submission_version_id"])
    try:
        with SessionLocal.begin() as session:
            session.execute(
                update(SubmissionVersion)
                .where(SubmissionVersion.id == first_version_id)
                .values(body="篡改旧版本")
            )
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("old SubmissionVersion update unexpectedly succeeded")
    try:
        with SessionLocal.begin() as session:
            session.execute(
                delete(SubmissionVersionAttachment).where(
                    SubmissionVersionAttachment.attachment_id == uuid.UUID(attachment["id"])
                )
            )
    except DBAPIError as error:
        assert "immutable" in str(error).lower()
    else:
        raise AssertionError("old SubmissionVersion attachment link deletion unexpectedly succeeded")

    with SessionLocal() as session:
        assert session.scalar(
            select(func.count(SubmissionVersion.id)).where(
                SubmissionVersion.submission_id == uuid.UUID(first["submission_id"])
            )
        ) == 2
        assert session.scalar(
            select(func.count(Review.id)).where(Review.assignment_id == uuid.UUID(assignment_id))
        ) == 2
        assert session.scalar(
            select(func.count(SubmissionDraft.id)).where(
                SubmissionDraft.assignment_id == uuid.UUID(assignment_id)
            )
        ) == 0


def test_concurrent_submit_retry_and_duplicate_command_create_one_version():
    learner, csrf_token, assignment_id, started = new_attachment_learner("concurrent-replay")
    payload = {
        "expected_revision": started["revision"],
        "body": submission_body("并发同幂等键"),
        "attachment_ids": [],
    }
    key = f"concurrent-submit-{uuid.uuid4()}"

    def submit(label: str, idempotency_key: str):
        concurrent = client_for(label)
        for cookie in learner.cookies.jar:
            concurrent.cookies.set(cookie.name, cookie.value)
        response = concurrent.post(
            f"/api/v1/me/assignments/{assignment_id}/submissions",
            headers={"Idempotency-Key": idempotency_key, "X-CSRF-Token": csrf_token},
            json=payload,
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        same_key_results = list(
            executor.map(lambda label: submit(label, key), ["same-key-a", "same-key-b"])
        )
    assert [status for status, _ in same_key_results] == [200, 200]
    result_ids = {
        result["data"]["submission_version_id"] for _, result in same_key_results
    }
    assert len(result_ids) == 1
    assert sorted(
        result["data"]["idempotency_replay"] for _, result in same_key_results
    ) == [False, True]

    learner_two, csrf_two, assignment_two, started_two = new_attachment_learner(
        "concurrent-conflict"
    )
    payload_two = {
        "expected_revision": started_two["revision"],
        "body": submission_body("并发不同幂等键"),
        "attachment_ids": [],
    }

    def submit_different(label: str):
        concurrent = client_for(label)
        for cookie in learner_two.cookies.jar:
            concurrent.cookies.set(cookie.name, cookie.value)
        return concurrent.post(
            f"/api/v1/me/assignments/{assignment_two}/submissions",
            headers={
                "Idempotency-Key": f"different-{label}-{uuid.uuid4()}",
                "X-CSRF-Token": csrf_two,
            },
            json=payload_two,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(submit_different, ["key-a", "key-b"]))
    assert statuses == [200, 409]
    with SessionLocal() as session:
        submission = session.scalar(
            select(Submission).where(Submission.assignment_id == uuid.UUID(assignment_two))
        )
        assert submission is not None and submission.current_version_no == 1
        assert session.scalar(
            select(func.count(SubmissionVersion.id)).where(
                SubmissionVersion.submission_id == submission.id
            )
        ) == 1
