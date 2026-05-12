import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr


class ServiceOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    duration_minutes: int
    price: Decimal
    is_active: bool

    model_config = {"from_attributes": True}


class BarberCreate(BaseModel):
    name: str
    bio: str | None = None
    phone: str
    email: EmailStr
    avatar_url: str | None = None


class BarberUpdate(BaseModel):
    name: str | None = None
    bio: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None


class ReviewSummary(BaseModel):
    rating: int
    comment: str | None
    customer_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BarberOut(BaseModel):
    id: uuid.UUID
    name: str
    bio: str | None
    phone: str
    email: str
    avatar_url: str | None
    is_active: bool
    services: list[ServiceOut] = []
    average_rating: float | None = None
    review_count: int = 0

    model_config = {"from_attributes": True}


class BarberDetail(BarberOut):
    reviews: list[ReviewSummary] = []


class ServiceCreate(BaseModel):
    name: str
    description: str | None = None
    duration_minutes: int
    price: Decimal
