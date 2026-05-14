import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

from app.services.phone import normalize_phone


class AppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    barber_id: uuid.UUID
    service_id: uuid.UUID
    scheduled_at: datetime
    notes: str | None = None

    @field_validator("customer_phone")
    @classmethod
    def normalize(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("scheduled_at")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            raise ValueError("scheduled_at must include timezone info")
        if v <= now:
            raise ValueError("Appointment must be scheduled in the future")
        return v


class AppointmentOut(BaseModel):
    id: uuid.UUID
    customer_name: str
    customer_phone: str
    customer_email: str | None
    barber_id: uuid.UUID
    service_id: uuid.UUID
    scheduled_at: datetime
    ends_at: datetime
    status: str
    notes: str | None
    created_at: datetime
    cancelled_at: datetime | None

    model_config = {"from_attributes": True}


class AvailableSlot(BaseModel):
    starts_at: datetime
    ends_at: datetime


class CancelResponse(BaseModel):
    message: str
    appointment_id: uuid.UUID


class CancelRequest(BaseModel):
    """Body for the in-app cancel endpoint.

    `customer_phone` is optional but strongly recommended — without it the
    server cannot verify the requester owns the appointment. We still allow
    omission for now to ease client adoption; the router controls policy.
    """

    customer_phone: str | None = None

    @field_validator("customer_phone")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            return None
        return normalize_phone(stripped)

