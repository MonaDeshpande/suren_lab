"""
services/exceptions.py
----------------------
Domain-specific exceptions for the LIMS application.

All domain errors subclass ValueError so existing callers and tests that
catch ValueError continue to work.
"""


class DomainError(ValueError):
    """Base class for business-rule violations."""


class UserAlreadyExistsError(DomainError):
    """Raised when registering a username that is already taken."""


class UserNotFoundError(DomainError):
    """Raised when a user id does not exist."""


class RoleAssignmentError(DomainError):
    """Raised when a role change violates lab policy (e.g. last admin)."""


class PasswordPolicyError(DomainError):
    """Raised when a password fails validation rules."""
