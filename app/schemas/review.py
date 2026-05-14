import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.services.phone import normalize_phone


class ReviewCreate(BaseModel):
    appointment_id: uuid.UUID
    rating: int
    comment: str | None = None
    customer_phone: str | None = None

    @field_validator("rating")
    @classmethod
    def rating_in_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("Rating must be between 1 and 5")
        return v

    @field_validator("customer_phone")
    @classmethod
    def normalize(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_phone(v)


class ReviewOut(BaseModel):
    id: uuid.UUID
    appointment_id: uuid.UUID
    barber_id: uuid.UUID
    rating: int
    comment: str | None
    customer_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
