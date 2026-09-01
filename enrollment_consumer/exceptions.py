class InvalidMessage(ValueError):
    """Raised when an SQS record body is not a valid enrollment request."""


class TenantLimitExceeded(RuntimeError):
    """Raised when a tenant has no free active-enrollment slots."""
