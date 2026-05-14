import logging
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.exceptions import (
    AppointmentStateError,
    CancellationWindowError,
    CustomerBlockedError,
    InvalidPhoneError,
    PhoneMismatchError,
    SlotUnavailableError,
)
from app.models import Appointment
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentOut,
    CancelRequest,
    CancelResponse,
)
from app.services import booking, sms
from app.services.phone import normalize_phone

logger = logging.getLogger(__name__)

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
    except CustomerBlockedError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "detail": str(exc),
                "blocked_until": exc.blocked_until.isoformat() if exc.blocked_until else None,
            },
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
async def cancel_appointment_via_token(
    token: str, session: AsyncSession = Depends(get_session)
) -> CancelResponse:
    """Legacy SMS deep-link cancel — preserved for the existing reminder flow."""
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


@router.post("/{appointment_id}/cancel", response_model=AppointmentOut)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: CancelRequest = Body(default_factory=CancelRequest),
    session: AsyncSession = Depends(get_session),
) -> AppointmentOut:
    """In-app cancel path with optional phone verification.

    Cancellation is allowed at any future time, but cancels inside 24h count
    as a strike against the customer (see `customer_service`). Errors map:

    - 404 — appointment doesn't exist
    - 403 — phone provided but didn't match the booking
    - 409 — appointment already cancelled / completed / past
    """
    try:
        appointment, is_late = await booking.cancel_appointment(
            session=session,
            appointment_id=appointment_id,
            customer_phone=payload.customer_phone,
        )
    except PhoneMismatchError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except AppointmentStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    sms.send_cancellation_confirmation(
        customer_name=appointment.customer_name,
        customer_phone=appointment.customer_phone,
        barber_name=appointment.barber.name,
        scheduled_at_str=appointment.scheduled_at.strftime("%b %d at %I:%M %p UTC"),
    )
    if is_late:
        logger.info("Late cancel recorded for appointment %s", appointment.id)

    return AppointmentOut.model_validate(appointment)


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(
    session: AsyncSession = Depends(get_session),
    phone: str | None = Query(default=None, description="Filter by E.164 or local phone"),
    limit: int | None = Query(default=None, ge=1, le=200),
) -> list[AppointmentOut]:
    """List appointments, optionally filtered by phone for guest recovery.

    No auth in v1 — anyone with a phone number could enumerate that
    customer's history. Acceptable trade-off for the POC; gate behind OTP
    later if abuse appears.
    """
    stmt = select(Appointment)
    if phone is not None:
        try:
            normalized = normalize_phone(phone)
        except InvalidPhoneError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        stmt = stmt.where(Appointment.customer_phone == normalized)
        stmt = stmt.order_by(Appointment.scheduled_at.desc())
    else:
        stmt = stmt.order_by(Appointment.scheduled_at)
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    return [AppointmentOut.model_validate(a) for a in result.scalars().all()]


@router.get("/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(appointment_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> AppointmentOut:
    appointment = await session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return AppointmentOut.model_validate(appointment)


@router.patch("/{appointment_id}/complete", response_model=AppointmentOut)
async def complete_appointment(
    appointment_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> AppointmentOut:
    try:
        appointment = await booking.complete_appointment(session, appointment_id)
    except AppointmentStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return AppointmentOut.model_validate(appointment)
