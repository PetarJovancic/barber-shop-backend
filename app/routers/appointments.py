import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.exceptions import CancellationWindowError, SlotUnavailableError
from app.models import Appointment, AppointmentStatus
from app.schemas.appointment import AppointmentCreate, AppointmentOut, CancelResponse
from app.services import booking, sms

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentOut, status_code=201)
async def book_appointment(
    payload: AppointmentCreate,
    session: AsyncSession = Depends(get_session),
) -> AppointmentOut:
    try:
        appointment = await booking.create_appointment(
            session=session,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            customer_email=payload.customer_email,
            barber_id=payload.barber_id,
            service_id=payload.service_id,
            scheduled_at=payload.scheduled_at,
            notes=payload.notes,
        )
    except SlotUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    cancellation_url = f"{settings.app_base_url}/api/appointments/cancel/{appointment.cancellation_token}"
    sms.send_booking_confirmation(
        customer_name=appointment.customer_name,
        customer_phone=appointment.customer_phone,
        barber_name=appointment.barber.name,
        service_name=appointment.service.name,
        scheduled_at_str=appointment.scheduled_at.strftime("%b %d at %I:%M %p UTC"),
        cancellation_url=cancellation_url,
    )

    return AppointmentOut.model_validate(appointment)


@router.get("/cancel/{token}", response_model=CancelResponse)
async def cancel_appointment(token: str, session: AsyncSession = Depends(get_session)) -> CancelResponse:
    try:
        appointment = await booking.cancel_by_token(session, token)
    except CancellationWindowError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    sms.send_cancellation_confirmation(
        customer_name=appointment.customer_name,
        customer_phone=appointment.customer_phone,
        barber_name=appointment.barber.name,
        scheduled_at_str=appointment.scheduled_at.strftime("%b %d at %I:%M %p UTC"),
    )

    return CancelResponse(message="Appointment cancelled successfully", appointment_id=appointment.id)


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(session: AsyncSession = Depends(get_session)) -> list[AppointmentOut]:
    result = await session.execute(select(Appointment).order_by(Appointment.scheduled_at))
    return [AppointmentOut.model_validate(a) for a in result.scalars().all()]


@router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(appointment_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> AppointmentOut:
    appointment = await session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return AppointmentOut.model_validate(appointment)


@router.patch("/{appointment_id}/complete", response_model=AppointmentOut)
async def complete_appointment(appointment_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> AppointmentOut:
    appointment = await session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status != AppointmentStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail=f"Cannot complete an appointment with status '{appointment.status}'")
    appointment.status = AppointmentStatus.COMPLETED
    await session.commit()
    await session.refresh(appointment)
    return AppointmentOut.model_validate(appointment)
