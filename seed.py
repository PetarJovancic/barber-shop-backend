"""Bootstrap the database with sample data for development."""

import asyncio
from decimal import Decimal

from app.database import AsyncSessionLocal, engine
from app.models import Appointment, Barber, Base, Service


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        haircut = Service(name="Haircut", description="Classic cut", duration_minutes=30, price=Decimal("25.00"))
        beard = Service(name="Beard Trim", description="Shape & trim", duration_minutes=20, price=Decimal("15.00"))
        full = Service(
            name="Full Service", description="Haircut + beard", duration_minutes=60, price=Decimal("35.00")
        )
        session.add_all([haircut, beard, full])
        await session.flush()

        marcus = Barber(
            name="Marcus Johnson",
            bio="15 years of experience. Specialist in fades and classic cuts.",
            phone="+1555000001",
            email="marcus@barbershop.com",
            services=[haircut, beard, full],
        )
        jay = Barber(
            name="Jay Reyes",
            bio="Creative cuts and beard styling expert.",
            phone="+1555000002",
            email="jay@barbershop.com",
            services=[haircut, full],
        )
        session.add_all([marcus, jay])

        await session.commit()
        print(f"Seeded: barbers={marcus.id}, {jay.id}")
        print(f"Seeded: services={haircut.id}, {beard.id}, {full.id}")


if __name__ == "__main__":
    asyncio.run(seed())
