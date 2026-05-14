import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Appointment, AppointmentStatus
from app.services import booking
from app.services.sms import send_reminder

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _sweep_no_shows() -> None:
    """Periodic sweep — flips appointments to no_show after a 1h grace window."""
    async with AsyncSessionLocal() as session:
        try:
            count = await booking.sweep_no_shows(session)
            if count:
                logger.info("No-show sweep: flipped %s appointments", count)
        except Exception:
            logger.exception("No-show sweep failed")


async def _send_pending_reminders() -> None:
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=settings.reminder_hours_before)
    window_end = window_start + timedelta(hours=1)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Appointment)
            .where(
                and_(
                    Appointment.status == AppointmentStatus.CONFIRMED,
                    Appointment.reminder_sent.is_(False),
                    Appointment.scheduled_at >= window_start,
                    Appointment.scheduled_at < window_end,
                )
            )
            .options(selectinload(Appointment.barber), selectinload(Appointment.service))
        )
        appointments = result.scalars().all()

        for appt in appointments:
            cancellation_url = f"{settings.app_base_url}/api/appointments/cancel/{appt.cancellation_token}"
            sent = send_reminder(
                customer_name=appt.customer_name,
                customer_phone=appt.customer_phone,
                barber_name=appt.barber.name,
                service_name=appt.service.name,
                scheduled_at_str=appt.scheduled_at.strftime("%b %d at %I:%M %p UTC"),
                cancellation_url=cancellation_url,
            )
            if sent:
                appt.reminder_sent = True
                logger.info("Reminder sent for appointment %s", appt.id)

        await session.commit()


def start_scheduler() -> None:
    scheduler.add_job(_send_pending_reminders, "interval", hours=1, id="reminders")
    scheduler.add_job(_sweep_no_shows, "interval", minutes=15, id="no_show_sweep")
    scheduler.start()
    logger.info("Background scheduler started (reminders + no-show sweep)")


def stop_scheduler() -> None:
    scheduler.shutdown()
