from __future__ import annotations

import logging
from typing import Any

from .exceptions import InvalidMessage, TenantLimitExceeded
from .models import EnrollmentRequest
from .repository import reserve_enrollment

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, list[dict[str, str]]]:
    """AWS Lambda handler for an SQS event-source mapping.

    Successful records, including idempotent no-ops, are omitted from
    ``batchItemFailures`` so AWS will not re-drive them.
    """
    failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = record.get("messageId")

        # A real SQS-trigger record always has messageId. Keeping this explicit
        # makes malformed local fixtures fail clearly without inventing an ID
        # that SQS could not use for partial-batch retry.
        if not isinstance(message_id, str) or not message_id:
            logger.error("SQS record is missing messageId")
            continue

        try:
            request = EnrollmentRequest.from_json(record.get("body"))
            outcome = reserve_enrollment(request, message_id=message_id)
            logger.info(
                "Processed SQS record message_id=%s outcome=%s",
                message_id,
                outcome.value,
            )
        except InvalidMessage as exc:
            logger.warning("Invalid SQS record message_id=%s: %s", message_id, exc)
            failures.append({"itemIdentifier": message_id})
        except TenantLimitExceeded as exc:
            logger.warning("Enrollment rejected message_id=%s: %s", message_id, exc)
            failures.append({"itemIdentifier": message_id})
        except Exception:
            # Includes transient DB failures and DB constraint violations.
            # Returning only this item lets successfully processed records in
            # the same SQS batch be deleted rather than retried.
            logger.exception("Failed to process SQS record message_id=%s", message_id)
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
