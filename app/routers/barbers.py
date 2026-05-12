import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import Barber, Service
from app.schemas.appointment import AvailableSlot
from app.schemas.barber import BarberCreate, BarberDetail, BarberOut, BarberUpdate, ServiceCreate, ServiceOut
from app.services.booking import get_available_slots

router = APIRouter(prefix="/barbers", tags=["barbers"])


@router.get("", response_model=list[BarberOut])
async def list_barbers(session: AsyncSession = Depends(get_session)) -> list[BarberOut]:
    result = await session.execute(
        select(Barber).where(Barber.is_active.is_(True)).options(selectinload(Barber.services), selectinload(Barber.reviews))
    )
    barbers = result.scalars().all()

    out = []
    for b in barbers:
        ratings = [r.rating for r in b.reviews]
        avg = round(sum(ratings) / len(ratings), 2) if ratings else None
        out.append(BarberOut(
            id=b.id, name=b.name, bio=b.bio, phone=b.phone, email=b.email,
            avatar_url=b.avatar_url, is_active=b.is_active, services=b.services,
            average_rating=avg, review_count=len(ratings),
        ))
    return out


@router.get("/services", response_model=list[ServiceOut])
async def list_services(session: AsyncSession = Depends(get_session)) -> list[ServiceOut]:
    result = await session.execute(select(Service).where(Service.is_active.is_(True)))
    return [ServiceOut.model_validate(s) for s in result.scalars().all()]


@router.post("/services", response_model=ServiceOut, status_code=201)
async def create_service(payload: ServiceCreate, session: AsyncSession = Depends(get_session)) -> ServiceOut:
    service = Service(**payload.model_dump())
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return ServiceOut.model_validate(service)


@router.get("/{barber_id}", response_model=BarberDetail)
async def get_barber(barber_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> BarberDetail:
    result = await session.execute(
        select(Barber).where(Barber.id == barber_id).options(
            selectinload(Barber.services), selectinload(Barber.reviews)
        )
    )
    barber = result.scalars().first()
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")

    ratings = [r.rating for r in barber.reviews]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else None
    return BarberDetail(
        id=barber.id, name=barber.name, bio=barber.bio, phone=barber.phone,
        email=barber.email, avatar_url=barber.avatar_url, is_active=barber.is_active,
        services=barber.services, average_rating=avg, review_count=len(ratings),
        reviews=barber.reviews,
    )


@router.get("/{barber_id}/availability")
async def get_availability(
    barber_id: uuid.UUID,
    date: date = Query(..., description="Date in YYYY-MM-DD format"),
    service_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_session),
):
    slots = await get_available_slots(session, barber_id, service_id, date)
    return [AvailableSlot(starts_at=s, ends_at=e) for s, e in slots]


@router.post("", response_model=BarberOut, status_code=201)
async def create_barber(payload: BarberCreate, session: AsyncSession = Depends(get_session)) -> BarberOut:
    barber = Barber(**payload.model_dump())
    session.add(barber)
    await session.commit()
    await session.refresh(barber)
    return BarberOut(
        id=barber.id, name=barber.name, bio=barber.bio, phone=barber.phone,
        email=barber.email, avatar_url=barber.avatar_url, is_active=barber.is_active,
        services=[], average_rating=None, review_count=0,
    )


@router.patch("/{barber_id}", response_model=BarberOut)
async def update_barber(
    barber_id: uuid.UUID,
    payload: BarberUpdate,
    session: AsyncSession = Depends(get_session),
) -> BarberOut:
    barber = await session.get(Barber, barber_id)
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(barber, field, value)
    await session.commit()
    await session.refresh(barber)
    return BarberOut(
        id=barber.id, name=barber.name, bio=barber.bio, phone=barber.phone,
        email=barber.email, avatar_url=barber.avatar_url, is_active=barber.is_active,
        services=[], average_rating=None, review_count=0,
    )


@router.post("/{barber_id}/services/{service_id}", status_code=204)
async def assign_service_to_barber(
    barber_id: uuid.UUID,
    service_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    barber = await session.get(Barber, barber_id, options=[selectinload(Barber.services)])
    if not barber:
        raise HTTPException(status_code=404, detail="Barber not found")
    service = await session.get(Service, service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    if service not in barber.services:
        barber.services.append(service)
        await session.commit()
