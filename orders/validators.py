"""Checkout's custom validators — small, pure, and unit-testable.

The card checks are plain functions that raise ``ValidationError``, and
the ZIP and discount-code shape rules are ``RegexValidator`` instances.
All are wired in through
``validators=[...]`` so every rule stays visible at the field
declaration. No form or view logic lives here.
"""

import datetime

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

# Shared by checkout's address fields and the saved ``Address`` model.
zip_validator = RegexValidator(
    r"^\d{5}(-\d{4})?$", "Enter a ZIP code like 79016 or 79016-1234."
)

# The shape of a stored discount code, checked after uppercasing.
discount_code_validator = RegexValidator(
    r"^[A-Z0-9-]+$", "Use letters, numbers, and dashes only."
)


def validate_card_number(value: str) -> None:
    """Reject a card number that fails the Luhn checksum.

    Spaces and hyphens are allowed, as people type them ("4242 4242
    4242 4242"). Standard test numbers such as 4242424242424242 and
    4111111111111111 pass; a single corrupted digit fails.
    """
    digits = value.replace(" ", "").replace("-", "")
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        raise ValidationError("Enter a valid card number.", code="card_number")

    total = 0
    for position, digit in enumerate(reversed(digits)):
        n = int(digit)
        if position % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    if total % 10 != 0:
        raise ValidationError("Enter a valid card number.", code="card_number")


def validate_expiry(value: str) -> None:
    """Reject an expiry that isn't MM/YY, or that is already in the past.

    The current month is still valid — a card expires at the end of its
    printed month, not the start.
    """
    try:
        month, year = value.split("/")
        if not (len(month) == 2 and month.isdigit() and len(year) == 2):
            raise ValueError
        expiry = datetime.date(2000 + int(year), int(month), 1)
    except (ValueError, TypeError):
        raise ValidationError(
            "Enter the expiry as MM/YY.", code="expiry_format"
        ) from None

    today = datetime.date.today()
    if expiry < today.replace(day=1):
        raise ValidationError("This card has expired.", code="expiry_past")
