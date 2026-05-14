import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.exceptions import (
    AppointmentStateError,
    CancellationWindowError,
    CustomerBlockedError,
    PhoneMismatchError,
    SlotUnavailableError,
)
from app.models import Appointment, AppointmentStatus, Customer, Service
from app.services import customers as customer_service

logger = logging.getLogger(__name__)

LATE_CANCEL_THRESHOLD_HOURS = 24
NO_SHOW_GRACE_HOURS = 1


async def get_available_slots(
    session: AsyncSession,
    barber_id: uuid.UUID,
    service_id: uuid.UUID,
    target_date: date,
) -> list[tuple[datetime, datetime]]:
    service = await session.get(Service, service_id)
    if not service:
        return []

    day_start = datetime(
        target_date.year, target_date.month, target_date.day, settings.business_open_hour, tzinfo=timezone.utc
    )
    day_close = datetime(
        target_date.year, target_date.month, target_date.day, settings.business_close_hour, tzinfo=timezone.utc
    )

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
    """Book an appointment.

    `customer_phone` is expected to be already E.164-normalized at the schema
    layer — keeping the normalization at the edge makes the service body
    purely about business rules.
    """
    existing_customer = await session.get(Customer, customer_phone)
    if existing_customer and customer_service.is_currently_blocked(existing_customer):
        raise CustomerBlockedError(
            f"Your phone is temporarily blocked from booking until "
            f"{existing_customer.blocked_until.isoformat() if existing_customer.blocked_until else 'further notice'}.",
            blocked_until=existing_customer.blocked_until,
        )

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

    await customer_service.get_or_create(session, phone=customer_phone, name=customer_name)

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
    """Legacy SMS deep-link cancel path: hard 2h window, no strike."""
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
    return appointment


async def cancel_appointment(
    session: AsyncSession,
    appointment_id: uuid.UUID,
    customer_phone: str | None,
) -> tuple[Appointment, bool]:
    """In-app cancel path: phone-verified, soft 24h "late cancel" window with strike.

    Unlike the token-based path, cancellation is *always* allowed as long as
    the appointment is still in the future and currently scheduled. Cancels
    inside the 24h window are recorded as a strike against the customer
    (they'll be blocked at threshold, see `customer_service`).

    Returns (appointment, is_late) — the boolean is hoisted up so the router
    can pick the right SMS template / response message if it wants to.
    """
    result = await session.execute(
        select(Appointment).where(Appointment.id == appointment_id).options(
            selectinload(Appointment.barber),
            selectinload(Appointment.service),
        )
    )
    appointment = result.scalars().first()
    if not appointment:
        raise ValueError("Appointment not found")

    if appointment.status != AppointmentStatus.CONFIRMED:
        raise AppointmentStateError(
            f"Cannot cancel an appointment with status '{appointment.status.value}'"
        )

    now = datetime.now(timezone.utc)
    if appointment.scheduled_at <= now:
        raise AppointmentStateError("Cannot cancel an appointment that has already started or passed")

    if customer_phone is not None and customer_phone != appointment.customer_phone:
        raise PhoneMismatchError("Phone number does not match this appointment")

    hours_until = (appointment.scheduled_at - now).total_seconds() / 3600.0
    is_late = hours_until < LATE_CANCEL_THRESHOLD_HOURS

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancelled_at = now

    if is_late:
        await customer_service.record_late_cancel(
            session, phone=appointment.customer_phone, name=appointment.customer_name
        )

    await session.commit()
    return appointment, is_late


async def complete_appointment(session: AsyncSession, appointment_id: uuid.UUID) -> Appointment:
    """Mark an appointment completed and reward the customer.

    Centralizing this in the service (rather than inline in the router) keeps
    the strike-reset side-effect inseparable from the status transition —
    callers can't accidentally complete an appointment without the reset.
    """
    result = await session.execute(
        select(Appointment).where(Appointment.id == appointment_id).options(
            selectinload(Appointment.barber),
            selectinload(Appointment.service),
        )
    )
    appointment = result.scalars().first()
    if not appointment:
        raise ValueError("Appointment not found")

    if appointment.status != AppointmentStatus.CONFIRMED:
        raise AppointmentStateError(
            f"Cannot complete an appointment with status '{appointment.status.value}'"
        )

    appointment.status = AppointmentStatus.COMPLETED
    await customer_service.reset_on_completion(
        session, phone=appointment.customer_phone, name=appointment.customer_name
    )
    await session.commit()
    return appointment


async def sweep_no_shows(session: AsyncSession) -> int:
    """Flip lingering scheduled appointments to NO_SHOW once the grace window passes.

    Returns the count of appointments transitioned. Designed to be idempotent
    so it's safe to run on any cadence — only `CONFIRMED` rows whose
    `scheduled_at + grace` lies in the past are touched.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=NO_SHOW_GRACE_HOURS)

    result = await session.execute(
        select(Appointment).where(
            and_(
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.scheduled_at <= cutoff,
            )
        )
    )
    candidates = result.scalars().all()

    for appt in candidates:
        appt.status = AppointmentStatus.NO_SHOW
        await customer_service.record_no_show(
            session, phone=appt.customer_phone, name=appt.customer_name
        )
        logger.info("Appointment %s flipped to no_show", appt.id)

    await session.commit()
    return len(candidates)
