"""Order placement — one of the codebase's two deliberate deep modules.

The interface is the product: one function that turns a cart and a
validated checkout into an order, all-or-nothing. Callers never touch
``Order`` construction directly.
"""

from collections.abc import Mapping
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from .models import ZERO, Address, Cart, DiscountCode, Order, OrderItem

ADDRESS_FIELDS = [
    "email",
    "shipping_name",
    "shipping_street",
    "shipping_line2",
    "shipping_city",
    "shipping_state",
    "shipping_zip",
    "billing_name",
    "billing_street",
    "billing_line2",
    "billing_city",
    "billing_state",
    "billing_zip",
]


@transaction.atomic
def place_order(
    cart: Cart,
    user: AbstractBaseUser,
    checkout_data: Mapping[str, Any],
    *,
    coupon_code: str | None = None,
    save_shipping_address: bool = False,
    save_billing_address: bool = False,
) -> Order:
    """Create an order from the cart's contents, then empty the cart.

    ``checkout_data`` is the ``cleaned_data`` of a valid ``CheckoutForm``.
    Addresses and line prices are denormalized onto the order — an order
    is a snapshot, immune to later catalog or address edits. Of the card,
    only the last four digits are stored; the full number and CVV never
    touch the database.

    ``coupon_code`` applies a ``DiscountCode`` (any case). Each covered
    line's discount is its total times the percent, rounded half-up to
    the cent; the order's discount is the sum of its lines', and
    ``total`` is charged after it. The code, percent, and amounts are
    copied onto the order and its lines, so later edits to the code —
    retiring, expiring, deleting — never change this order.

    ``save_shipping_address`` and ``save_billing_address`` also copy that
    address into the user's address book — skipped when an identical
    address is already saved, and claiming the matching default slot if
    the user has none. Both default to ``False``: nothing is saved unless
    asked.

    All-or-nothing: runs in a transaction, so a failure partway through
    leaves no partial order, no newly saved address, and the cart intact.

    Raises ``ValueError`` if the cart is empty or holds a product that is
    no longer available, and ``InvalidDiscountCode`` (a ``ValueError``)
    if ``coupon_code`` is unknown, retired, expired, or covers nothing in
    the cart — the code is re-checked here, whatever the form said.
    """
    lines = list(cart.lines())
    if not lines:
        raise ValueError("Cannot place an order from an empty cart.")
    unavailable = [line.product.name for line in lines if not line.product.is_available]
    if unavailable:
        raise ValueError(
            f"No longer available: {', '.join(unavailable)}. "
            "Remove them from the cart to check out."
        )

    code = None
    if coupon_code:
        code = DiscountCode.objects.redeem(
            coupon_code, [line.product for line in lines]
        )
    line_discounts = [
        code.discount_on(line.product, line.line_total) if code else ZERO
        for line in lines
    ]
    discount = sum(line_discounts, ZERO)

    card_digits = checkout_data["card_number"].replace(" ", "").replace("-", "")
    order = Order.objects.create(
        user=user,
        total=cart.total() - discount,
        card_last4=card_digits[-4:],
        discount=code,
        discount_code=code.code if code else "",
        discount_percent=code.percent if code else None,
        discount_amount=discount,
        **{name: checkout_data[name] for name in ADDRESS_FIELDS},
    )
    for line, line_discount in zip(lines, line_discounts, strict=True):
        OrderItem.objects.create(
            order=order,
            product=line.product,
            product_name=line.product.name,
            unit_price=line.product.price,
            quantity=line.quantity,
            discount_amount=line_discount,
        )
    if save_shipping_address:
        Address.objects.save_unique(
            user, as_shipping=True, **_address_from(checkout_data, "shipping")
        )
    if save_billing_address:
        Address.objects.save_unique(
            user, as_billing=True, **_address_from(checkout_data, "billing")
        )
    cart.items.all().delete()
    return order


def _address_from(checkout_data: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    """One section of the checkout as ``Address`` fields, prefix stripped."""
    return {field: checkout_data[f"{prefix}_{field}"] for field in Address.FIELDS}
