"""Bind notification events and actors to one fixed organization scope.

Revision ID: 0009_notification_scope
Revises: 0008_outcome_notifications
"""

from alembic import op


revision = "0009_notification_scope"
down_revision = "0008_outcome_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("fk_outbox_events_owner", "outbox_events", type_="foreignkey")
    op.drop_constraint("fk_outbox_events_actor", "outbox_events", type_="foreignkey")
    op.create_foreign_key(
        "fk_outbox_events_owner_scope",
        "outbox_events",
        "users",
        ["owner_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_outbox_events_actor_scope",
        "outbox_events",
        "users",
        ["actor_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_unique_constraint(
        "uq_outbox_notification_fixed_scope",
        "outbox_events",
        ["id", "organization_id", "owner_id", "aggregate_id"],
    )
    op.drop_constraint(
        "fk_notification_deliveries_event",
        "notification_deliveries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_notification_deliveries_event_scope",
        "notification_deliveries",
        "outbox_events",
        ["event_id", "organization_id", "recipient_user_id", "outcome_id"],
        ["id", "organization_id", "owner_id", "aggregate_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_notification_deliveries_event_scope",
        "notification_deliveries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_notification_deliveries_event",
        "notification_deliveries",
        "outbox_events",
        ["event_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_outbox_notification_fixed_scope", "outbox_events", type_="unique"
    )
    op.drop_constraint(
        "fk_outbox_events_actor_scope", "outbox_events", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_outbox_events_owner_scope", "outbox_events", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_outbox_events_actor",
        "outbox_events",
        "users",
        ["actor_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_outbox_events_owner",
        "outbox_events",
        "users",
        ["owner_id"],
        ["id"],
    )
