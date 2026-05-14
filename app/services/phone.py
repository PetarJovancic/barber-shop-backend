"""Phone number normalization.

Keeps a single canonical form (E.164) everywhere in the system so that
"+381 65 806 3859", "+38165 8063859", and "065 806 3859" all collapse to
"+381658063859". Storing/comparing only the canonical form removes a whole
class of bugs around string equality on user-entered phones.
"""

import phonenumbers

from app.exceptions import InvalidPhoneError

DEFAULT_REGION = "RS"


def normalize_phone(raw: str, default_region: str = DEFAULT_REGION) -> str:
    """Parse a user-entered phone and return the E.164 form.

    The default region lets locals enter "065 806 3859" without country code.
    Numbers entered with an explicit "+" or international prefix are parsed
    region-agnostically.
    """
    if not raw or not raw.strip():
        raise InvalidPhoneError("Phone number is required")

    try:
        parsed = phonenumbers.parse(raw.strip(), default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneError(f"Could not parse phone number: {exc}") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneError("Invalid phone number")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
