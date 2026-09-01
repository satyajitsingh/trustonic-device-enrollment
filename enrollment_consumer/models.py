from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .exceptions import InvalidMessage


@dataclass(frozen=True, slots=True)
class EnrollmentRequest:
    imei: str
    tenant_id: str
    device_type: str
    requested_at: datetime

    @classmethod
    def from_json(cls, body: str) -> "EnrollmentRequest":
        try:
            payload: Any = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise InvalidMessage("body must be valid JSON") from exc

        if not isinstance(payload, dict):
            raise InvalidMessage("body must be a JSON object")

        imei = _required_string(payload, "imei")
        tenant_id = _required_string(payload, "tenant_id")
        device_type = _required_string(payload, "device_type")
        requested_at_raw = _required_string(payload, "requested_at")

        try:
            requested_at = datetime.fromisoformat(
                requested_at_raw.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise InvalidMessage("requested_at must be ISO-8601") from exc

        if requested_at.tzinfo is None:
            raise InvalidMessage("requested_at must include a timezone")

        return cls(
            imei=imei,
            tenant_id=tenant_id,
            device_type=device_type,
            requested_at=requested_at,
        )


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidMessage(f"{key} must be a non-empty string")
    return value.strip()
