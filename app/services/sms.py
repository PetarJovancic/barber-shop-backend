import logging

from twilio.rest import Client

from app.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client | None:
    global _client
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        return None
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


def send_sms(to: str, body: str) -> bool:
    client = _get_client()
    if not client:
        logger.warning("Twilio not configured — SMS skipped: %s", body)
        return False
    try:
        client.messages.create(to=to, from_=settings.twilio_from_number, body=body)
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", to)
        return False


def send_booking_confirmation(
    customer_name: str,
    customer_phone: str,
    barber_name: str,
    service_name: str,
    scheduled_at_str: str,
    cancellation_url: str,
) -> bool:
    body = (
        f"Hi {customer_name}! Your appointment with {barber_name} "
        f"for {service_name} is confirmed for {scheduled_at_str}. "
        f"To cancel (at least 2h before): {cancellation_url}"
    )
    return send_sms(customer_phone, body)


def send_reminder(
    customer_name: str,
    customer_phone: str,
    barber_name: str,
    service_name: str,
    scheduled_at_str: str,
    cancellation_url: str,
) -> bool:
    body = (
        f"Reminder: Hi {customer_name}, your appointment with {barber_name} "
        f"for {service_name} is tomorrow at {scheduled_at_str}. "
        f"Need to cancel? {cancellation_url}"
    )
    return send_sms(customer_phone, body)


def send_cancellation_confirmation(
    customer_name: str,
    customer_phone: str,
    barber_name: str,
    scheduled_at_str: str,
) -> bool:
    body = (
        f"Hi {customer_name}, your appointment with {barber_name} "
        f"on {scheduled_at_str} has been cancelled. See you next time!"
    )
    return send_sms(customer_phone, body)
