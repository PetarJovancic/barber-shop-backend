# Barber Shop API

FastAPI backend for the barber shop booking system. Handles barbers, services, appointments, reviews, and SMS notifications.

## Stack

- **Python 3.12** + FastAPI
- **PostgreSQL** via SQLAlchemy 2.0 async
- **Twilio** for SMS (confirmation, reminders, cancellation)
- **APScheduler** for 24h reminder background job
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
DATABASE_URL=postgresql+asyncpg://barber:barber@localhost:5432/barber_shop

# Optional — SMS won't send without these
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1234567890

APP_BASE_URL=http://localhost:8000
```

**3. Start PostgreSQL**
```bash
docker compose up db -d
```

**4. Run the server**
```bash
uv run poe localserver
```

The API is now at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

**5. Seed sample data (optional)**
```bash
uv run python seed.py
```

This creates 2 barbers and 3 services to start testing immediately.

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/barbers` | List all active barbers |
| GET | `/api/barbers/{id}` | Barber profile with services and reviews |
| GET | `/api/barbers/{id}/availability?date=YYYY-MM-DD&service_id=...` | Available time slots |
| POST | `/api/barbers` | Create a barber |
| PATCH | `/api/barbers/{id}` | Update a barber |
| GET | `/api/barbers/services` | List all services |
| POST | `/api/barbers/services` | Create a service |
| POST | `/api/barbers/{id}/services/{service_id}` | Assign service to barber |
| POST | `/api/appointments` | Book an appointment (sends confirmation SMS) |
| GET | `/api/appointments/cancel/{token}` | Cancel appointment via token (enforces 2h window) |
| POST | `/api/reviews` | Submit a review for a completed appointment |
| GET | `/api/reviews/barber/{barber_id}` | Get reviews for a barber |

## Business Rules

- **Business hours**: 9 AM – 7 PM (configurable via `BUSINESS_OPEN_HOUR` / `BUSINESS_CLOSE_HOUR`)
- **Cancellation window**: minimum 2 hours before appointment (configurable via `MIN_CANCEL_HOURS`)
- **Reminders**: sent 24h before appointment via a background job that runs every hour (configurable via `REMINDER_HOURS_BEFORE`)
- **Reviews**: only allowed for appointments with status `completed`

## Running with Docker (full stack)

```bash
docker compose up
```

This starts both the API and PostgreSQL. The API will be at `http://localhost:8000`.

## Project Structure

```
app/
├── main.py          # FastAPI app, lifespan (DB init + scheduler)
├── config.py        # Settings from environment
├── database.py      # Async SQLAlchemy engine + session
├── models.py        # ORM models: Barber, Service, Appointment, Review
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
    ├── booking.py    # Slot conflict detection, appointment creation, cancellation logic
    ├── sms.py        # Twilio wrapper
    └── reminders.py  # APScheduler job for 24h reminders
```
