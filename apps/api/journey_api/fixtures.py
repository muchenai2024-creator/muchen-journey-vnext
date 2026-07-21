import uuid

ORGANIZATION_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
LEARNER_ID = uuid.UUID("10000000-0000-4000-8000-000000000002")
REVIEWER_ID = uuid.UUID("10000000-0000-4000-8000-000000000003")
LEARNER_ROLE_ID = uuid.UUID("10000000-0000-4000-8000-000000000004")
REVIEWER_ROLE_ID = uuid.UUID("10000000-0000-4000-8000-000000000005")
TASK_VERSION_ID = uuid.UUID("10000000-0000-4000-8000-000000000006")
ENROLLMENT_ID = uuid.UUID("10000000-0000-4000-8000-000000000007")
ASSIGNMENT_ID = uuid.UUID("10000000-0000-4000-8000-000000000008")
OPERATOR_ID = uuid.UUID("10000000-0000-4000-8000-000000000009")
OPERATOR_ROLE_ID = uuid.UUID("10000000-0000-4000-8000-00000000000a")
TASK_DEFINITION_ID = uuid.UUID("10000000-0000-4000-8000-00000000000b")
TASK_VERSION_V2_ID = uuid.UUID("10000000-0000-4000-8000-00000000000c")

# This is the public, synthetic-data contract for the one canonical fixture
# builder. It intentionally records schema coverage and stable references, but
# never copies display names, tokens, submission bodies, feedback, or other
# person-like values into evidence.
FIXTURE_MANIFEST = {
    "schema_version": 1,
    "classification": "SYNTHETIC_NO_REAL_PII",
    "builder": "python -m journey_api.seed",
    "stable_references": {
        "organization": str(ORGANIZATION_ID),
        "learner": str(LEARNER_ID),
        "reviewer": str(REVIEWER_ID),
        "operator": str(OPERATOR_ID),
        "task_definition": str(TASK_DEFINITION_ID),
        "task_version_v1": str(TASK_VERSION_ID),
        "task_version_v2": str(TASK_VERSION_V2_ID),
        "enrollment": str(ENROLLMENT_ID),
        "assignment": str(ASSIGNMENT_ID),
    },
    "tables": {
        "organizations": ["id", "name"],
        "users": ["id", "organization_id", "display_name", "status"],
        "role_assignments": ["id", "organization_id", "user_id", "role"],
        "task_definitions": [
            "id",
            "organization_id",
            "stable_key",
            "status",
            "revision",
            "created_by",
        ],
        "task_versions": [
            "id",
            "organization_id",
            "task_definition_id",
            "version",
            "content_contract",
            "publish_evidence",
        ],
        "enrollments": ["id", "organization_id", "learner_id", "status"],
        "assignments": [
            "id",
            "organization_id",
            "enrollment_id",
            "task_definition_id",
            "task_version_id",
            "owner_id",
            "status",
            "revision",
            "position",
        ],
    },
    "excluded_value_classes": [
        "real_person_identity",
        "email_or_phone",
        "invite_or_session_token",
        "submission_or_feedback_body",
        "attachment_bytes",
        "tenant_app_domain_ip_or_secret",
    ],
}
