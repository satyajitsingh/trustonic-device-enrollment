# Trustonic Device Enrollment Consumer

Python AWS Lambda consumer for SQS device-enrollment events. It reserves active enrollment slots in Postgres, is idempotent under SQS redelivery, enforces a per-tenant active-device limit under concurrent Lambda invocations, and returns the AWS partial-batch-failure response shape.

## Requirements

- Python 3.12+
- Docker / Docker Compose (for the local Postgres used by tests)

