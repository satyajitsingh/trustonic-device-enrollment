CREATE TABLE IF NOT EXISTS tenant_limits (
    tenant_id TEXT PRIMARY KEY,
    device_limit INTEGER NOT NULL DEFAULT 5 CHECK (device_limit >= 0)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant_limits (tenant_id),
    imei TEXT NOT NULL,
    device_type TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    de_enrolled_at TIMESTAMPTZ NULL,
    CHECK ((active = TRUE AND de_enrolled_at IS NULL) OR active = FALSE)
);

-- Database-level defence against consuming more than one active slot for the
-- same tenant/device pair. Historical inactive enrollments remain possible.
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_enrollment_per_device
    ON enrollments (tenant_id, imei)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS ix_enrollments_tenant_active
    ON enrollments (tenant_id, active);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    imei TEXT NOT NULL,
    outcome TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
