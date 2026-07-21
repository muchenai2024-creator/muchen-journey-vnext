"""Grant the staging runtime role DML-only access after Alembic owns the schema."""

from sqlalchemy import create_engine, text


RUNTIME_ROLE = "journey_next_runtime"


def main() -> None:
    engine = create_engine(__import__("os").environ["DATABASE_URL"])
    statements = (
        f"GRANT CONNECT ON DATABASE journey_next_staging TO {RUNTIME_ROLE}",
        f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {RUNTIME_ROLE}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {RUNTIME_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {RUNTIME_ROLE}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {RUNTIME_ROLE}",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
    engine.dispose()


if __name__ == "__main__":
    main()
