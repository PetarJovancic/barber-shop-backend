import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import Appointment, AppointmentStatus, Review
from app.schemas.review import ReviewCreate, ReviewOut

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=201)
async def create_review(payload: ReviewCreate, session: AsyncSession = Depends(get_session)) -> ReviewOut:
    result = await session.execute(
        select(Appointment).where(Appointment.id == payload.appointment_id).options(
            selectinload(Appointment.review)
        )
    )
    appointment = result.scalars().first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status != AppointmentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Reviews can only be submitted for completed appointments")
    if appointment.review:
        raise HTTPException(status_code=409, detail="A review already exists for this appointment")

    review = Review(
        appointment_id=appointment.id,
        barber_id=appointment.barber_id,
        rating=payload.rating,
        comment=payload.comment,
        customer_name=appointment.customer_name,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return ReviewOut.model_validate(review)


@router.get("/barber/{barber_id}", response_model=list[ReviewOut])
async def get_barber_reviews(barber_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[ReviewOut]:
    result = await session.execute(select(Review).where(Review.barber_id == barber_id).order_by(Review.created_at.desc()))
    reviews = result.scalars().all()
    return [ReviewOut.model_validate(r) for r in reviews]
