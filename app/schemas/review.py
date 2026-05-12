import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class ReviewCreate(BaseModel):
    appointment_id: uuid.UUID
    rating: int
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def rating_in_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("Rating must be between 1 and 5")
        return v


class ReviewOut(BaseModel):
    id: uuid.UUID
    appointment_id: uuid.UUID
    barber_id: uuid.UUID
    rating: int
    comment: str | None
    customer_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
