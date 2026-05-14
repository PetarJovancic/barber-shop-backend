class SlotUnavailableError(Exception):
    pass


class CancellationWindowError(Exception):
    pass


class ReviewAlreadyExistsError(Exception):
    pass


class InvalidPhoneError(ValueError):
    """Raised when a phone number cannot be normalized to E.164."""


class PhoneMismatchError(Exception):
    """Raised when the supplied phone does not match the appointment's stored phone."""


class CustomerBlockedError(Exception):
    """Raised when a temporarily-blocked customer attempts to book."""

    def __init__(self, message: str, blocked_until: object) -> None:
        super().__init__(message)
        self.blocked_until = blocked_until


class AppointmentStateError(Exception):
    """Raised when an appointment is in a state that doesn't allow the requested action."""
