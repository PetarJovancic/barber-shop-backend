"""Bootstrap the database with sample data for development.

Safe to run multiple times: barbers and services are matched by stable keys
(email / name) and updated in place; demo appointments are removed and
re-created so reviews stay consistent with the schema.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal, engine
from app.models import Appointment, AppointmentStatus, Barber, Base, Review, Service

# Stable dummy portrait URLs (Lorem Picsum — no assets to host locally).
AVATAR_MARCUS = "https://picsum.photos/id/64/400/400"
AVATAR_JAY = "https://picsum.photos/id/338/400/400"

# Demo customers — used to wipe/re-seed sample appointments + reviews only.
DEMO_CUSTOMER_PHONES = (
    "+381601112223",
    "+381602223334",
    "+381603334445",
    "+381604445556",
    "+381605556667",
    "+381606667778",
    "+381607778889",
    "+381608889990",
    "+381609990001",
    "+381600011122",
    "+381600122233",
    "+381600233344",
)


async def _get_service_by_name(session, name: str) -> Service | None:
    result = await session.execute(select(Service).where(Service.name == name))
    return result.scalars().first()


async def _ensure_service(
    session,
    *,
    name: str,
    description: str,
    duration_minutes: int,
    price: Decimal,
) -> Service:
    existing = await _get_service_by_name(session, name)
    if existing is not None:
        return existing
    row = Service(
        name=name,
        description=description,
        duration_minutes=duration_minutes,
        price=price,
    )
    session.add(row)
    await session.flush()
    return row


async def _get_barber_by_email(session, email: str) -> Barber | None:
    result = await session.execute(
        select(Barber).where(Barber.email == email).options(selectinload(Barber.services))
    )
    return result.scalars().first()


def _attach_services(barber: Barber, services: list[Service]) -> None:
    for svc in services:
        if svc not in barber.services:
            barber.services.append(svc)


async def _ensure_barber(
    session,
    *,
    email: str,
    name: str,
    bio: str,
    phone: str,
    avatar_url: str,
    services: list[Service],
) -> Barber:
    existing = await _get_barber_by_email(session, email)
    if existing is not None:
        existing.name = name
        existing.bio = bio
        existing.phone = phone
        existing.avatar_url = avatar_url
        _attach_services(existing, services)
        return existing

    row = Barber(
        name=name,
        bio=bio,
        phone=phone,
        email=email,
        avatar_url=avatar_url,
        services=list(services),
    )
    session.add(row)
    await session.flush()
    return row


async def _clear_demo_appointments_and_reviews(session) -> None:
    result = await session.execute(
        select(Appointment.id).where(Appointment.customer_phone.in_(DEMO_CUSTOMER_PHONES))
    )
    ids = [row[0] for row in result.all()]
    if not ids:
        return
    await session.execute(delete(Review).where(Review.appointment_id.in_(ids)))
    await session.execute(delete(Appointment).where(Appointment.id.in_(ids)))


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        haircut = await _ensure_service(
            session,
            name="Haircut",
            description="Classic cut",
            duration_minutes=30,
            price=Decimal("25.00"),
        )
        beard = await _ensure_service(
            session,
            name="Beard Trim",
            description="Shape & trim",
            duration_minutes=20,
            price=Decimal("15.00"),
        )
        full = await _ensure_service(
            session,
            name="Full Service",
            description="Haircut + beard",
            duration_minutes=60,
            price=Decimal("35.00"),
        )

        marcus = await _ensure_barber(
            session,
            email="marcus@barbershop.com",
            name="Marcus Johnson",
            bio="15 years of experience. Specialist in fades and classic cuts.",
            phone="+1555000001",
            avatar_url=AVATAR_MARCUS,
            services=[haircut, beard, full],
        )
        jay = await _ensure_barber(
            session,
            email="jay@barbershop.com",
            name="Jay Reyes",
            bio="Creative cuts and beard styling expert.",
            phone="+1555000002",
            avatar_url=AVATAR_JAY,
            services=[haircut, full],
        )

        await _clear_demo_appointments_and_reviews(session)

        now = datetime.now(timezone.utc)

        def past_slot(days_ago: int, hour: int, minute: int) -> datetime:
            base = now - timedelta(days=days_ago)
            return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

        completed_rows: list[tuple[Appointment, int, str | None, str]] = [
            (
                Appointment(
                    customer_name="Ana Marković",
                    customer_phone="+381601112223",
                    customer_email=None,
                    barber_id=marcus.id,
                    service_id=haircut.id,
                    scheduled_at=past_slot(14, 10, 0),
                    ends_at=past_slot(14, 10, 0) + timedelta(minutes=haircut.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                5,
                "Best fade in town — will book again.",
                "Ana Marković",
            ),
            (
                Appointment(
                    customer_name="Luka Petrović",
                    customer_phone="+381602223334",
                    customer_email="luka@example.com",
                    barber_id=marcus.id,
                    service_id=full.id,
                    scheduled_at=past_slot(21, 14, 30),
                    ends_at=past_slot(21, 14, 30) + timedelta(minutes=full.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                4,
                "Great attention to detail on the beard line.",
                "Luka Petrović",
            ),
            (
                Appointment(
                    customer_name="Mila Jovanović",
                    customer_phone="+381603334445",
                    customer_email=None,
                    barber_id=jay.id,
                    service_id=haircut.id,
                    scheduled_at=past_slot(10, 11, 0),
                    ends_at=past_slot(10, 11, 0) + timedelta(minutes=haircut.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                5,
                "Super friendly and fast without rushing.",
                "Mila Jovanović",
            ),
            (
                Appointment(
                    customer_name="Stefan Nikolić",
                    customer_phone="+381604445556",
                    customer_email=None,
                    barber_id=jay.id,
                    service_id=full.id,
                    scheduled_at=past_slot(30, 16, 0),
                    ends_at=past_slot(30, 16, 0) + timedelta(minutes=full.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                4,
                None,
                "Stefan Nikolić",
            ),
            (
                Appointment(
                    customer_name="Jovana Stanković",
                    customer_phone="+381605556667",
                    customer_email=None,
                    barber_id=marcus.id,
                    service_id=beard.id,
                    scheduled_at=past_slot(7, 9, 30),
                    ends_at=past_slot(7, 9, 30) + timedelta(minutes=beard.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                5,
                "Beard shape was exactly what I asked for.",
                "Jovana Stanković",
            ),
            (
                Appointment(
                    customer_name="Nikola Đorđević",
                    customer_phone="+381606667778",
                    customer_email="nikola@example.com",
                    barber_id=marcus.id,
                    service_id=haircut.id,
                    scheduled_at=past_slot(18, 12, 0),
                    ends_at=past_slot(18, 12, 0) + timedelta(minutes=haircut.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                4,
                "Solid cut, on time, fair price.",
                "Nikola Đorđević",
            ),
            (
                Appointment(
                    customer_name="Sara Ilić",
                    customer_phone="+381607778889",
                    customer_email=None,
                    barber_id=marcus.id,
                    service_id=haircut.id,
                    scheduled_at=past_slot(45, 15, 0),
                    ends_at=past_slot(45, 15, 0) + timedelta(minutes=haircut.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                5,
                "Marcus listens — rare skill. Highly recommend.",
                "Sara Ilić",
            ),
            (
                Appointment(
                    customer_name="Petar Kostić",
                    customer_phone="+381608889990",
                    customer_email=None,
                    barber_id=jay.id,
                    service_id=haircut.id,
                    scheduled_at=past_slot(5, 10, 30),
                    ends_at=past_slot(5, 10, 30) + timedelta(minutes=haircut.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                5,
                "Clean fade, chill vibe in the chair.",
                "Petar Kostić",
            ),
            (
                Appointment(
                    customer_name="Ivana Radović",
                    customer_phone="+381609990001",
                    customer_email=None,
                    barber_id=jay.id,
                    service_id=full.id,
                    scheduled_at=past_slot(60, 13, 0),
                    ends_at=past_slot(60, 13, 0) + timedelta(minutes=full.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                4,
                "Full service was worth it — haircut and beard both on point.",
                "Ivana Radović",
            ),
            (
                Appointment(
                    customer_name="Marko Todorović",
                    customer_phone="+381600011122",
                    customer_email=None,
                    barber_id=marcus.id,
                    service_id=full.id,
                    scheduled_at=past_slot(33, 17, 30),
                    ends_at=past_slot(33, 17, 30) + timedelta(minutes=full.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                3,
                "Good overall — a bit rushed at the end but happy with the result.",
                "Marko Todorović",
            ),
            (
                Appointment(
                    customer_name="Teodora Vasić",
                    customer_phone="+381600122233",
                    customer_email=None,
                    barber_id=jay.id,
                    service_id=haircut.id,
                    scheduled_at=past_slot(12, 9, 0),
                    ends_at=past_slot(12, 9, 0) + timedelta(minutes=haircut.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                5,
                "Jay remembered how I like my neckline from last time.",
                "Teodora Vasić",
            ),
            (
                Appointment(
                    customer_name="Dušan Pavlović",
                    customer_phone="+381600233344",
                    customer_email=None,
                    barber_id=marcus.id,
                    service_id=beard.id,
                    scheduled_at=past_slot(25, 11, 15),
                    ends_at=past_slot(25, 11, 15) + timedelta(minutes=beard.duration_minutes),
                    status=AppointmentStatus.COMPLETED,
                    reminder_sent=True,
                ),
                4,
                "Sharp lines, no irritation after.",
                "Dušan Pavlović",
            ),
        ]

        for appt, rating, comment, reviewer_name in completed_rows:
            session.add(appt)
        await session.flush()

        for appt, rating, comment, reviewer_name in completed_rows:
            session.add(
                Review(
                    appointment_id=appt.id,
                    barber_id=appt.barber_id,
                    rating=rating,
                    comment=comment,
                    customer_name=reviewer_name,
                )
            )

        await session.commit()
        print(f"Seeded: barbers={marcus.id}, {jay.id}")
        print(f"Seeded: services={haircut.id}, {beard.id}, {full.id}")
        print(f"Seeded: {len(completed_rows)} completed appointments with reviews (idempotent)")


if __name__ == "__main__":
    asyncio.run(seed())
