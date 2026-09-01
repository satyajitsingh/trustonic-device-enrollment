from __future__ import annotations

import os
from enum import StrEnum

import psycopg

from .exceptions import TenantLimitExceeded
from .models import EnrollmentRequest


class EnrollmentOutcome(StrEnum):
    ENROLLED = "enrolled"
    DUPLICATE_MESSAGE = "duplicate_message"
    ALREADY_ACTIVE = "already_active"


def reserve_enrollment(
    request: EnrollmentRequest,
    *,
    message_id: str,
) -> EnrollmentOutcome:
    """Atomically reserve one active slot for ``(tenant_id, imei)``.

    The tenant row is locked for the transaction, serialising all enrollment
    decisions for that tenant while still allowing different tenants to be
    processed concurrently.
    """
    database_url = os.environ["DATABASE_URL"]
    default_limit = int(os.getenv("DEFAULT_DEVICE_LIMIT", "5"))

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Make tenant creation safe when two first-ever events for the same
            # tenant arrive concurrently.
            cur.execute(
                """
                INSERT INTO tenant_limits (tenant_id, device_limit)
                VALUES (%s, %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (request.tenant_id, default_limit),
            )

            # The key concurrency control: all decisions affecting one tenant's
            # quota are serialised on this row until commit/rollback.
            cur.execute(
                """
                SELECT device_limit
                FROM tenant_limits
                WHERE tenant_id = %s
                FOR UPDATE
                """,
                (request.tenant_id,),
            )
            tenant_row = cur.fetchone()
            if tenant_row is None:
                raise RuntimeError("tenant row disappeared during transaction")
            device_limit = int(tenant_row[0])

            # Exact SQS redelivery after a previous successful commit.
            cur.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = %s",
                (message_id,),
            )
            if cur.fetchone() is not None:
                return EnrollmentOutcome.DUPLICATE_MESSAGE

            # Exercise semantics: if this device is already actively enrolled,
            # processing is a successful no-op and consumes no additional slot.
            cur.execute(
                """
                SELECT 1
                FROM enrollments
                WHERE tenant_id = %s
                  AND imei = %s
                  AND active = TRUE
                """,
                (request.tenant_id, request.imei),
            )
            if cur.fetchone() is not None:
                _mark_message_processed(
                    cur,
                    message_id=message_id,
                    request=request,
                    outcome=EnrollmentOutcome.ALREADY_ACTIVE,
                )
                return EnrollmentOutcome.ALREADY_ACTIVE

            cur.execute(
                """
                SELECT COUNT(*)
                FROM enrollments
                WHERE tenant_id = %s
                  AND active = TRUE
                """,
                (request.tenant_id,),
            )
            active_count = int(cur.fetchone()[0])

            if active_count >= device_limit:
                # The exception causes the surrounding psycopg connection
                # context manager to roll back the whole record transaction.
                raise TenantLimitExceeded(
                    f"tenant {request.tenant_id!r} has reached its "
                    f"active device limit of {device_limit}"
                )

            cur.execute(
                """
                INSERT INTO enrollments (
                    tenant_id,
                    imei,
                    device_type,
                    requested_at,
                    active
                )
                VALUES (%s, %s, %s, %s, TRUE)
                """,
                (
                    request.tenant_id,
                    request.imei,
                    request.device_type,
                    request.requested_at,
                ),
            )

            _mark_message_processed(
                cur,
                message_id=message_id,
                request=request,
                outcome=EnrollmentOutcome.ENROLLED,
            )

            return EnrollmentOutcome.ENROLLED


def _mark_message_processed(
    cur: psycopg.Cursor,
    *,
    message_id: str,
    request: EnrollmentRequest,
    outcome: EnrollmentOutcome,
) -> None:
    cur.execute(
        """
        INSERT INTO processed_messages (
            message_id,
            tenant_id,
            imei,
            outcome
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (message_id) DO NOTHING
        """,
        (message_id, request.tenant_id, request.imei, outcome.value),
    )
