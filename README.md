# Barber Shop API

FastAPI backend for the barber shop booking system. Handles barbers, services, appointments, reviews, and SMS notifications.

## Stack

- **Python 3.12** + FastAPI
- **PostgreSQL** via SQLAlchemy 2.0 async
- **Twilio** for SMS (confirmation, reminders, cancellation)
- **APScheduler** for 24h reminders (hourly) and no-show sweep (every 15 minutes)
- **uv** for package management

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker (for PostgreSQL)

## Setup

**1. Clone and install dependencies**
```bash
uv sync
```

**2. Configure environment**
```bash
cp .env.example .env
```

Edit `.env` — the only required change for local dev is leaving the default `DATABASE_URL`. Twilio fields are optional (SMS is skipped gracefully if not set):

```env
DATABASE_URL=postgresql+asyncpg://barber:barber@localhost:5410/barber_shop

# Optional — SMS won't send without these
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890

APP_BASE_URL=http://localhost:8000
```

**3. Run the server**
```bash
uv run poe localserver
```

This starts PostgreSQL, runs migrations, and starts the server in one command. The script first runs `docker compose down -v` (via `uv run poe services-down-v`), then brings Postgres back up — so **each run starts from an empty database**, even if a previous session did not shut down cleanly. When the server process ends (`Ctrl+C`, SIGTERM, or uvicorn exiting), the same `down -v` runs again so containers and the volume are removed. Re-run `uv run python seed.py` whenever you want the sample dataset after a fresh start.

The API is now at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

**4. Seed sample data (optional)**
```bash
uv run python seed.py
```

Creates 2 barbers (with dummy `avatar_url`s), 3 services, several completed appointments, and reviews so list/detail endpoints have data to hit immediately.

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check — returns `{"status": "ok"}` |
| GET | `/api/barbers` | List all active barbers |
| GET | `/api/barbers/{id}` | Barber profile with services and reviews |
| GET | `/api/barbers/{id}/availability?date=YYYY-MM-DD&service_id=...` | Available time slots |
| POST | `/api/barbers` | Create a barber |
| PATCH | `/api/barbers/{id}` | Update a barber |
| GET | `/api/barbers/services` | List all services |
| POST | `/api/barbers/services` | Create a service |
| POST | `/api/barbers/{id}/services/{service_id}` | Assign service to barber |
| GET | `/api/appointments` | List appointments (default: all, ascending by `scheduled_at`). Optional `?phone=<E.164 or local>` filters by normalized phone (descending by `scheduled_at`); optional `&limit=` (1–200) caps results |
| GET | `/api/appointments/{id}` | Get a single appointment |
| POST | `/api/appointments` | Book an appointment (body: customer, phone, optional email, barber/service IDs, `scheduled_at`, optional notes). Sends confirmation SMS when Twilio is configured; **403** if phone is temporarily blocked |
| PATCH | `/api/appointments/{id}/complete` | Mark appointment as completed (resets customer strike counters) |
| POST | `/api/appointments/{id}/cancel` | In-app cancel. Body (JSON): `{ "customer_phone": "+381..." }` optional but recommended — if sent, must match the booking or **403**. Future + `confirmed` only; **409** if wrong state/past. Cancels within 24h of start count as a late-cancel strike |
| GET | `/api/appointments/cancel/{token}` | SMS deep-link cancel (no body). **409** if inside the hard cancel window (`MIN_CANCEL_HOURS` before start) |
| POST | `/api/reviews` | Submit a review. Body: `appointment_id`, `rating` (1–5), optional `comment`, optional `customer_phone` (if present, must match appointment or **403**). **404** / **400** / **409** per rules in Business Rules |
| GET | `/api/reviews/barber/{barber_id}` | List reviews for a barber (newest first) |

## Business Rules

- **Business hours**: 9 AM – 7 PM (configurable via `BUSINESS_OPEN_HOUR` / `BUSINESS_CLOSE_HOUR`)
- **Cancellation windows**:
  - Token cancel (`GET /api/appointments/cancel/{token}`): hard window — must cancel ≥ 2h before (`MIN_CANCEL_HOURS`)
  - In-app cancel (`POST /api/appointments/{id}/cancel`): always allowed for future appointments, but cancels inside 24h count as a "late cancel" strike
- **Reminders**: sent 24h before appointment via a background job that runs every hour (configurable via `REMINDER_HOURS_BEFORE`)
- **No-show detection**: a sweep job runs every 15 min, flipping any still-`confirmed` appointment to `no_show` 1 hour after `scheduled_at` and incrementing the customer's strike count
- **Reviews**: only allowed when the appointment is `completed` *and* `scheduled_at` is in the past. Server enforces the unique-per-appointment rule and (optionally) phone match
- **Anti-abuse**:
  - Customers are tracked in a `customers` table keyed by E.164 phone (`late_cancel_count`, `no_show_count`, `is_blocked`, `blocked_until`)
  - When `late_cancel_count + no_show_count >= 2`, the customer is blocked for 30 days and `POST /api/appointments` returns 403
  - Completing an appointment resets both counters (rewards good behavior)
- **Phone normalization**: all phone inputs (booking, cancel body, `?phone=` query, reviews) are parsed via [`phonenumbers`](https://pypi.org/project/phonenumbers/) with default region `RS` (Serbia) and stored/compared as E.164. `"+381 65 806 3859"`, `"+38165 8063859"`, and `"065 806 3859"` all collapse to `"+381658063859"`.

## Other commands

```bash
# DB shell
PGPASSWORD=barber psql -p 5410 -h localhost -U barber -d barber_shop

# Start/stop DB only
uv run poe services-up
uv run poe services-down          # stop containers; keeps the postgres_data volume
uv run poe services-down-v        # stop containers and remove volume (wipe all DB data)
```

## Project Structure

```
app/
├── main.py          # FastAPI app, lifespan (DB init + scheduler)
├── config.py        # Settings from environment
├── database.py      # Async SQLAlchemy engine + session
├── models.py        # ORM models: Barber, Service, Appointment, Review, Customer
├── exceptions.py    # Domain exceptions
├── routers/
│   ├── barbers.py       # Barber + service endpoints
│   ├── appointments.py  # Booking + cancellation endpoints
│   └── reviews.py       # Review endpoints
├── schemas/
│   ├── barber.py        # Pydantic request/response schemas
│   ├── appointment.py
│   └── review.py
└── services/
    ├── booking.py     # Slot conflict detection, create/cancel/complete, no-show sweep
    ├── customers.py   # Strike counters + block enforcement (single source of policy)
    ├── phone.py       # E.164 normalization (default region RS)
    ├── sms.py         # Twilio wrapper
    └── reminders.py   # APScheduler: 24h reminders + no-show sweep
```
