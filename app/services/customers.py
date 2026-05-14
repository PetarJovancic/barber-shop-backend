"""Customer aggregate: strike counters, block enforcement, completion rewards.

Single source of truth for "is this phone allowed to book?" Anything that
mutates strike counts or the block flag goes through here, so policy lives
in one place. The booking service just *calls* these functions — it doesn't
know the strike threshold or the block duration, which makes those policy
knobs trivially tunable later.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer

STRIKE_THRESHOLD = 2
BLOCK_DURATION_DAYS = 30


async def get_or_create(session: AsyncSession, *, phone: str, name: str) -> Customer:
    """Fetch a customer by E.164 phone, creating them on first booking.

    Caller is responsible for committing — this function just stages changes
    in the session so it composes cleanly inside a larger transaction.
    """
    customer = await session.get(Customer, phone)
    if customer is None:
        customer = Customer(phone=phone, name=name)
        session.add(customer)
        await session.flush()
    return customer


def is_currently_blocked(customer: Customer) -> bool:
    """Block expires automatically when blocked_until passes."""
    if not customer.is_blocked:
        return False
    if customer.blocked_until is None:
        return True
    return customer.blocked_until > datetime.now(timezone.utc)


def _maybe_block(customer: Customer) -> None:
    """Apply the block rule when total strikes hit the threshold."""
    total_strikes = customer.late_cancel_count + customer.no_show_count
    if total_strikes >= STRIKE_THRESHOLD:
        customer.is_blocked = True
        customer.blocked_until = datetime.now(timezone.utc) + timedelta(days=BLOCK_DURATION_DAYS)


async def record_late_cancel(session: AsyncSession, *, phone: str, name: str) -> Customer:
    customer = await get_or_create(session, phone=phone, name=name)
    customer.late_cancel_count += 1
    _maybe_block(customer)
    return customer


async def record_no_show(session: AsyncSession, *, phone: str, name: str) -> Customer:
    customer = await get_or_create(session, phone=phone, name=name)
    customer.no_show_count += 1
    _maybe_block(customer)
    return customer


async def reset_on_completion(session: AsyncSession, *, phone: str, name: str) -> Customer:
    """Reward good behavior — wipe strike counters when an appointment completes.

    Per spec we only reset counters; we deliberately leave `blocked_until` to
    expire on its own. A previously-blocked customer who manages to complete
    a booking has effectively earned a clean slate going forward, but we
    don't retroactively shorten an active block.
    """
    customer = await get_or_create(session, phone=phone, name=name)
    customer.late_cancel_count = 0
    customer.no_show_count = 0
    return customer
