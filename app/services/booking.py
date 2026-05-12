import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.exceptions import CancellationWindowError, SlotUnavailableError
from app.models import Appointment, AppointmentStatus, Service


async def get_available_slots(
    session: AsyncSession,
    barber_id: uuid.UUID,
    service_id: uuid.UUID,
    target_date: date,
) -> list[tuple[datetime, datetime]]:
    service = await session.get(Service, service_id)
    if not service:
        return []

    day_start = datetime(target_date.year, target_date.month, target_date.day, settings.business_open_hour, tzinfo=timezone.utc)
    day_close = datetime(target_date.year, target_date.month, target_date.day, settings.business_close_hour, tzinfo=timezone.utc)

    all_slots = []
    slot = day_start
    while slot + timedelta(minutes=service.duration_minutes) <= day_close:
        all_slots.append(slot)
        slot += timedelta(minutes=service.duration_minutes)

    if not all_slots:
        return []

    result = await session.execute(
        select(Appointment).where(
            and_(
                Appointment.barber_id == barber_id,
                Appointment.status != AppointmentStatus.CANCELLED,
                Appointment.scheduled_at >= day_start,
                Appointment.scheduled_at < day_close + timedelta(days=1),
            )
        )
    )
    booked = result.scalars().all()

    available = []
    for start in all_slots:
        end = start + timedelta(minutes=service.duration_minutes)
        conflict = any(not (end <= appt.scheduled_at or start >= appt.ends_at) for appt in booked)
        if not conflict:
            available.append((start, end))

    return available


async def create_appointment(
    session: AsyncSession,
    customer_name: str,
    customer_phone: str,
    customer_email: str | None,
    barber_id: uuid.UUID,
    service_id: uuid.UUID,
    scheduled_at: datetime,
    notes: str | None,
) -> Appointment:
    service = await session.get(Service, service_id)
    if not service:
        raise ValueError("Service not found")

    ends_at = scheduled_at + timedelta(minutes=service.duration_minutes)

    result = await session.execute(
        select(Appointment).where(
            and_(
                Appointment.barber_id == barber_id,
                Appointment.status != AppointmentStatus.CANCELLED,
                Appointment.scheduled_at < ends_at,
                Appointment.ends_at > scheduled_at,
            )
        )
    )
    if result.scalars().first():
        raise SlotUnavailableError("This time slot is already booked")

    appointment = Appointment(
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_email=customer_email,
        barber_id=barber_id,
        service_id=service_id,
        scheduled_at=scheduled_at,
        ends_at=ends_at,
        notes=notes,
    )
    session.add(appointment)
    await session.flush()
    await session.refresh(appointment, ["barber", "service"])
    await session.commit()
    return appointment


async def cancel_by_token(session: AsyncSession, token: str) -> Appointment:
    result = await session.execute(
        select(Appointment).where(Appointment.cancellation_token == token).options(
            selectinload(Appointment.barber),
            selectinload(Appointment.service),
        )
    )
    appointment = result.scalars().first()
    if not appointment:
        raise ValueError("Appointment not found")

    if appointment.status == AppointmentStatus.CANCELLED:
        raise ValueError("Appointment is already cancelled")

    now = datetime.now(timezone.utc)
    deadline = appointment.scheduled_at - timedelta(hours=settings.min_cancel_hours)
    if now > deadline:
        raise CancellationWindowError(
            f"Cancellations must be made at least {settings.min_cancel_hours}h before the appointment"
        )

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = now
    await session.commit()
    await session.refresh(appointment)
    return appointment
