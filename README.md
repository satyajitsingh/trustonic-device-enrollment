# Trustonic Device Enrollment Consumer

Python AWS Lambda consumer for SQS device-enrollment events. It reserves active enrollment slots in Postgres, is idempotent under SQS redelivery, enforces a per-tenant active-device limit under concurrent Lambda invocations, and returns the AWS partial-batch-failure response shape.

## Requirements

- Python 3.12+
- Docker / Docker Compose (for the local Postgres used by tests)

## Run locally

```bash
docker compose up -d db
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/enrollment
export TEST_DATABASE_URL=$DATABASE_URL
export DEFAULT_DEVICE_LIMIT=5
```

Apply the schema:

```bash
psql "$DATABASE_URL" -f migrations/001_init.sql
```

Run the tests:

```bash
pytest
```

The tests use a real local Postgres rather than SQLite because the concurrency requirement depends on Postgres transaction/row-lock behaviour. Each test truncates the three exercise tables before running.

## Lambda handler

Configure the Lambda handler as:

```text
enrollment_consumer.handler.lambda_handler
```

The handler expects the normal SQS event-source mapping shape:

```json
{
  "Records": [
    {
      "messageId": "message-1",
      "body": "{\"imei\":\"356938035643809\",\"tenant_id\":\"test-int\",\"device_type\":\"smartphone\",\"requested_at\":\"2026-08-19T10:00:00Z\"}"
    }
  ]
}
```

and returns:

```json
{
  "batchItemFailures": [
    {"itemIdentifier": "failed-message-id"}
  ]
}
```

Only failed records are returned. Successful enrollments and idempotent no-ops are omitted so SQS will not reprocess them.

## Concurrency approach

Every tenant has one row in `tenant_limits`. Enrollment runs in a transaction and acquires `SELECT ... FOR UPDATE` on that tenant row before checking the active count and inserting. This serialises quota-changing decisions for one tenant while allowing unrelated tenants to proceed concurrently.

A partial unique index on `(tenant_id, imei) WHERE active = TRUE` is a second database-level idempotency defence.

## Local database / test harness

- Local database: Postgres 16 via Docker Compose.
- Test harness: pytest invokes the Lambda handler with realistic `{"Records": [...]}` fixtures.
- The concurrency test starts two Lambda-handler calls in separate threads against the same tenant with a limit of one and asserts that exactly one enrollment succeeds.

## Notes for AWS deployment

For a production Lambda/RDS deployment I would normally place RDS Proxy between Lambda and Postgres (or otherwise manage warm connection reuse) to avoid connection storms during Lambda scale-out. The exercise keeps connection ownership explicit and per-record for isolation and readability.

The SQS event-source mapping must have `ReportBatchItemFailures` enabled for the returned `batchItemFailures` list to control per-record retries.
