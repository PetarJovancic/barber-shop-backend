import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine
from app.models import Base
from app.routers import appointments, barbers, reviews
from app.services.reminders import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.execute(text("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'no_show'"))
        except Exception:
            logger.exception(
                "Could not ensure 'no_show' enum value (run an alembic migration if upgrading)"
            )
    start_scheduler()
    yield
    stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title="Barber Shop API",
    description="Booking system for barber shops — POC",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(barbers.router, prefix="/api")
app.include_router(appointments.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
