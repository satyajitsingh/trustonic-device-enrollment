from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from enrollment_consumer.handler import lambda_handler

from .conftest import active_count, enrollment_count, set_tenant_limit


def sqs_record(
    message_id: str,
    *,
    tenant_id: str = "test-int",
    imei: str = "356938035643809",
    device_type: str = "smartphone",
    requested_at: str = "2026-08-19T10:00:00Z",
) -> dict:
    return {
        "messageId": message_id,
        "body": json.dumps(
            {
                "imei": imei,
                "tenant_id": tenant_id,
                "device_type": device_type,
                "requested_at": requested_at,
            }
        ),
    }


def test_clean_successful_enrollment() -> None:
    event = {"Records": [sqs_record("msg-1")]}

    result = lambda_handler(event, None)

    assert result == {"batchItemFailures": []}
    assert enrollment_count("test-int", "356938035643809") == 1
    assert active_count("test-int") == 1


def test_duplicate_message_is_idempotent() -> None:
    event = {"Records": [sqs_record("msg-duplicate")]}

    first = lambda_handler(event, None)
    second = lambda_handler(event, None)

    assert first == {"batchItemFailures": []}
    assert second == {"batchItemFailures": []}
    assert enrollment_count("test-int", "356938035643809") == 1
    assert active_count("test-int") == 1


def test_concurrent_attempt_cannot_exceed_tenant_limit() -> None:
    tenant_id = "tenant-concurrent"
    set_tenant_limit(tenant_id, 1)
    barrier = threading.Barrier(2)

    event_a = {
        "Records": [
            sqs_record(
                "msg-a",
                tenant_id=tenant_id,
                imei="111111111111111",
            )
        ]
    }
    event_b = {
        "Records": [
            sqs_record(
                "msg-b",
                tenant_id=tenant_id,
                imei="222222222222222",
            )
        ]
    }

    def invoke(event: dict) -> dict:
        barrier.wait(timeout=5)
        return lambda_handler(event, None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(invoke, [event_a, event_b]))

    failure_ids = {
        failure["itemIdentifier"]
        for result in results
        for failure in result["batchItemFailures"]
    }

    assert active_count(tenant_id) == 1
    assert len(failure_ids) == 1
    assert failure_ids <= {"msg-a", "msg-b"}


def test_partial_batch_returns_only_failed_records() -> None:
    # Fill this tenant's only slot first.
    tenant_id = "tenant-full"
    set_tenant_limit(tenant_id, 1)
    existing = sqs_record(
        "setup-message",
        tenant_id=tenant_id,
        imei="333333333333333",
    )
    assert lambda_handler({"Records": [existing]}, None) == {
        "batchItemFailures": []
    }

    malformed = {
        "messageId": "msg-malformed",
        "body": json.dumps(
            {
                "tenant_id": "tenant-ok",
                "device_type": "smartphone",
                "requested_at": "2026-08-19T10:00:00Z",
            }
        ),
    }

    event = {
        "Records": [
            sqs_record(
                "msg-success",
                tenant_id="tenant-ok",
                imei="444444444444444",
            ),
            malformed,
            sqs_record(
                "msg-limit",
                tenant_id=tenant_id,
                imei="555555555555555",
            ),
            # Same active device but a new SQS message: successful no-op under
            # the exercise's stated idempotency semantics.
            sqs_record(
                "msg-already-active",
                tenant_id=tenant_id,
                imei="333333333333333",
            ),
        ]
    }

    result = lambda_handler(event, None)

    assert result == {
        "batchItemFailures": [
            {"itemIdentifier": "msg-malformed"},
            {"itemIdentifier": "msg-limit"},
        ]
    }
    assert active_count("tenant-ok") == 1
    assert active_count(tenant_id) == 1
