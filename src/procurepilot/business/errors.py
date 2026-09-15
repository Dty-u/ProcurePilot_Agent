"""Explicit errors raised by deterministic procurement rules."""


class DomainError(Exception):
    """Base class for procurement domain failures."""


class DomainValidationError(DomainError, ValueError):
    """A domain object would violate one of its invariants."""


class InactiveEntityError(DomainError):
    """An inactive supplier or part was used for procurement."""


class CurrencyMismatchError(DomainError):
    """Values with different currencies were combined."""


class InvalidOrderStateError(DomainError):
    """An order state transition is not permitted."""


class ImmutableOrderError(DomainError):
    """A terminal order was modified."""


class EntityNotFoundError(DomainError):
    """A requested business entity does not exist."""


class ConflictError(DomainError):
    """A uniqueness, idempotency, or optimistic-version conflict occurred."""


class PermissionDeniedError(DomainError):
    """The current actor is not allowed to perform an operation."""


class ApprovalRequiredError(DomainError):
    """A protected write does not have a valid approval."""


class InfrastructureError(DomainError):
    """An infrastructure operation failed without exposing implementation details."""
