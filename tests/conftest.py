from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest


TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/enrollment",
)


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> None:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    migration_path = Path(__file__).parents[1] / "migrations" / "001_init.sql"
    migration_sql = migration_path.read_text(encoding="utf-8")

    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        for statement in migration_sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)


@pytest.fixture(autouse=True)
def clean_database() -> None:
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE processed_messages, enrollments, tenant_limits "
            "RESTART IDENTITY CASCADE"
        )


def set_tenant_limit(tenant_id: str, limit: int) -> None:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute(
            """
            INSERT INTO tenant_limits (tenant_id, device_limit)
            VALUES (%s, %s)
            ON CONFLICT (tenant_id)
            DO UPDATE SET device_limit = EXCLUDED.device_limit
            """,
            (tenant_id, limit),
        )


def active_count(tenant_id: str) -> int:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM enrollments
            WHERE tenant_id = %s AND active = TRUE
            """,
            (tenant_id,),
        ).fetchone()
        return int(row[0])


def enrollment_count(tenant_id: str, imei: str) -> int:
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM enrollments
            WHERE tenant_id = %s AND imei = %s
            """,
            (tenant_id, imei),
        ).fetchone()
        return int(row[0])
