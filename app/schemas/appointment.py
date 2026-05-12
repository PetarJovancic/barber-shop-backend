import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class AppointmentCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    barber_id: uuid.UUID
    service_id: uuid.UUID
    scheduled_at: datetime
    notes: str | None = None

    @field_validator("scheduled_at")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        from datetime import timezone
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
