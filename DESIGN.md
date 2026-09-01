- **Atomic per-tenant limit**
  - Use one `tenant_limits` row per tenant and lock it with `SELECT ... FOR UPDATE` inside the same transaction as the active-count check and enrollment insert.
  - Serialises quota-changing operations only for the same tenant; different tenants can still process concurrently.
  - Prefer this over check-then-insert because the latter races across Lambda invocations.
  - Prefer this over `SERIALIZABLE` for the exercise because explicit tenant locking is easier to reason about and avoids transaction-retry machinery for expected contention.
  - Prefer this over a Postgres advisory lock because a real row makes the lock scope visible in the data model and naturally carries the configurable per-tenant limit.
  - Keep a partial unique index on `(tenant_id, imei) WHERE active = TRUE` as database-level defence for per-device idempotency.

- **Meaning of actively enrolled**
  - `enrollments.active = TRUE` consumes one tenant slot.
  - `active = FALSE` does not consume a slot and allows a future enrollment for the same `(tenant_id, imei)`.
  - Include nullable `de_enrolled_at` in the schema so de-enrollment/expiry can be added without changing the core model.
  - Do not implement a de-enrollment event path in the two-hour exercise because it is outside the requested consumer scope.

- **Duplicate delivery vs new enrollment attempt for the same device**
  - Store each successfully handled SQS `messageId` in `processed_messages`; the same `messageId` is an exact redelivery.
  - Treat a different `messageId` for an already-active `(tenant_id, imei)` as a successful no-op because the exercise explicitly requires an already-active device not to consume another slot.
  - Treat a different `messageId` after the previous enrollment has become inactive as a genuine new enrollment attempt.
  - Prefer a producer-generated immutable `event_id` over SQS `messageId` in a real cross-queue/event-replay design.

- **DB commit succeeds but Lambda fails before SQS acknowledgement**
  - Postgres already contains the enrollment and `processed_messages` row when SQS redelivers.
  - Redelivery sees the same processed `messageId` and returns success without consuming another slot.
  - The partial unique active-enrollment index also prevents a second active row for the same tenant/device if application logic regresses.
  - Preserve the standard at-least-once SQS model rather than attempting distributed exactly-once delivery.

- **With more time**
  - Add LocalStack with a real SQS queue, Lambda deployment and event-source mapping for an end-to-end test.
  - Add explicit RDS Proxy configuration and warm-connection management for Lambda scale-out.
  - Add retries/backoff for known transient Postgres errors while keeping retries bounded by Lambda timeout.
  - Add structured metrics for enrolled, duplicate, already-active, quota-rejected, invalid and DB-error outcomes.
  - Add DLQ/redrive configuration so permanently invalid or quota-blocked messages do not retry forever.
  - Add migration tooling such as Alembic rather than a single SQL migration file.
  - Add de-enrollment/expiry handling and tests around slot release and subsequent re-enrollment.
  - Add stricter domain validation for IMEI/device type once those business rules are specified.
