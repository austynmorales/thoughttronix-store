"""Discount codes: the model's rules, place_order's discounting and
snapshot, the checkout form and preview, and the back-office screens."""

from datetime import timedelta
from decimal import Decimal
from http import HTTPStatus

import pytest
from django.db import IntegrityError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from products.models import Product

from .forms import CheckoutForm
from .models import CartItem, DiscountCode, InvalidDiscountCode, Order
from .services import place_order
from .test_checkout_form import VALID_DATA

# --- The model ----------------------------------------------------------------


def test_codes_are_stored_trimmed_and_uppercased(db):
    code = DiscountCode.objects.create(code="  thoughts10 ", percent=10)

    assert code.code == "THOUGHTS10"


def test_percent_must_be_between_1_and_100(db):
    with pytest.raises(IntegrityError):
        DiscountCode.objects.create(code="FREE", percent=101)


def test_status_follows_the_switch_and_the_clock(order_wide_code):
    assert order_wide_code.status == DiscountCode.Status.ACTIVE

    order_wide_code.expires_at = timezone.now() + timedelta(days=1)
    assert order_wide_code.status == DiscountCode.Status.ACTIVE

    order_wide_code.expires_at = timezone.now() - timedelta(minutes=1)
    assert order_wide_code.status == DiscountCode.Status.EXPIRED

    order_wide_code.is_active = False  # retired beats expired
    assert order_wide_code.status == DiscountCode.Status.RETIRED


def test_an_order_wide_code_covers_every_product(order_wide_code, product):
    assert order_wide_code.is_order_wide
    assert order_wide_code.covers(product)


def test_a_product_code_covers_only_its_products(product_code, featured_product):
    assert not product_code.is_order_wide
    assert product_code.covers(product_code.products.get())
    assert not product_code.covers(featured_product)
    assert product_code.discount_on(featured_product, Decimal("89.00")) == Decimal(
        "0.00"
    )


def test_discounts_round_half_up_to_the_cent(order_wide_code, product):
    assert order_wide_code.discount_on(product, Decimal("0.05")) == Decimal("0.01")
    assert order_wide_code.discount_on(product, Decimal("699.98")) == Decimal("70.00")


# --- Redeeming ----------------------------------------------------------------


def test_redeem_ignores_case_and_spaces(order_wide_code, product):
    assert DiscountCode.objects.redeem(" thoughts10 ", [product]) == order_wide_code


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"code": "OTHER"}, "don't recognize"),
        ({"is_active": False}, "no longer active"),
        ({"expires_at": timezone.now() - timedelta(days=1)}, "has expired"),
    ],
)
def test_redeem_rejects_with_a_reason(order_wide_code, product, change, message):
    DiscountCode.objects.filter(pk=order_wide_code.pk).update(**change)

    with pytest.raises(InvalidDiscountCode, match=message):
        DiscountCode.objects.redeem("THOUGHTS10", [product])


def test_redeem_rejects_a_code_that_covers_nothing(product_code, featured_product):
    with pytest.raises(InvalidDiscountCode, match="doesn't apply"):
        DiscountCode.objects.redeem("HUB20", [featured_product])


def test_an_invalid_code_is_a_value_error():
    assert issubclass(InvalidDiscountCode, ValueError)


# --- place_order --------------------------------------------------------------


@pytest.fixture
def two_line_cart(cart, cart_item, featured_product):
    """2 × Home Hub at $349.99 and 1 × Desk Lamp at $89.00 — $788.98."""
    cart.add(featured_product)
    return cart


def test_an_order_wide_code_discounts_every_line(two_line_cart, order_wide_code):
    order = place_order(
        two_line_cart, two_line_cart.user, dict(VALID_DATA), coupon_code="thoughts10"
    )

    hub, lamp = order.items.all()
    assert hub.discount_amount == Decimal("70.00")  # 69.998, rounded half-up
    assert lamp.discount_amount == Decimal("8.90")
    assert order.discount_amount == Decimal("78.90")
    assert order.total == Decimal("710.08")
    assert order.subtotal == Decimal("788.98")


def test_a_product_code_discounts_only_its_lines(two_line_cart, product_code):
    order = place_order(
        two_line_cart, two_line_cart.user, dict(VALID_DATA), coupon_code="HUB20"
    )

    hub, lamp = order.items.all()
    assert hub.discount_amount == Decimal("140.00")
    assert lamp.discount_amount == Decimal("0.00")
    assert order.discount_amount == Decimal("140.00")
    assert order.total == Decimal("648.98")


def test_the_discount_is_copied_onto_the_order(two_line_cart, order_wide_code):
    order = place_order(
        two_line_cart, two_line_cart.user, dict(VALID_DATA), coupon_code="THOUGHTS10"
    )

    assert order.discount == order_wide_code
    assert order.discount_code == "THOUGHTS10"
    assert order.discount_percent == 10


def test_line_discounts_always_sum_to_the_order_discount(
    cart, category, order_wide_code
):
    for i, price in enumerate(["0.05", "0.15", "1.25", "19.95"]):
        cart.add(
            Product.objects.create(
                name=f"Odd {i}",
                slug=f"odd-{i}",
                price=Decimal(price),
                category=category,
            )
        )

    order = place_order(cart, cart.user, dict(VALID_DATA), coupon_code="THOUGHTS10")

    assert order.discount_amount == sum(i.discount_amount for i in order.items.all())
    assert order.total + order.discount_amount == Decimal("21.40")


def test_retiring_editing_or_deleting_the_code_leaves_the_order_alone(
    cart, cart_item, order_wide_code
):
    order = place_order(cart, cart.user, dict(VALID_DATA), coupon_code="THOUGHTS10")

    order_wide_code.percent = 50
    order_wide_code.is_active = False
    order_wide_code.save()
    order_wide_code.delete()

    order.refresh_from_db()
    assert order.discount is None  # the live link goes; the copy stays
    assert order.discount_code == "THOUGHTS10"
    assert order.discount_percent == 10
    assert order.discount_amount == Decimal("70.00")
    assert order.total == Decimal("629.98")


def test_an_invalid_code_places_nothing_and_keeps_the_cart(cart, cart_item):
    with pytest.raises(InvalidDiscountCode):
        place_order(cart, cart.user, dict(VALID_DATA), coupon_code="NOPE")

    assert not Order.objects.exists()
    assert CartItem.objects.count() == 1


def test_a_code_that_covers_nothing_in_the_cart_is_rejected(
    cart, featured_product, product_code
):
    cart.add(featured_product)

    with pytest.raises(InvalidDiscountCode, match="doesn't apply"):
        place_order(cart, cart.user, dict(VALID_DATA), coupon_code="HUB20")

    assert not Order.objects.exists()


# --- The checkout form --------------------------------------------------------


def test_a_valid_code_cleans_to_its_stored_form(cart, cart_item, order_wide_code):
    form = CheckoutForm(data={**VALID_DATA, "discount_code": " thoughts10"}, cart=cart)

    assert form.is_valid()
    assert form.cleaned_data["discount_code"] == "THOUGHTS10"


def test_the_code_is_optional(cart, cart_item):
    form = CheckoutForm(data=VALID_DATA, cart=cart)

    assert form.is_valid()
    assert form.cleaned_data["discount_code"] == ""


def test_a_bad_code_errors_beside_its_own_field(cart, cart_item, order_wide_code):
    order_wide_code.is_active = False
    order_wide_code.save()

    form = CheckoutForm(data={**VALID_DATA, "discount_code": "THOUGHTS10"}, cart=cart)

    assert not form.is_valid()
    assert form.errors == {"discount_code": ["That discount code is no longer active."]}


# --- The checkout page --------------------------------------------------------


@pytest.fixture
def shopper(client, cart, cart_item):
    """A signed-in customer with 2 × Home Hub ($699.98) in the cart."""
    client.force_login(cart.user)
    return client


def test_the_preview_shows_the_discounted_total(shopper, order_wide_code):
    response = shopper.post(
        reverse("orders:discount_preview"), {"discount_code": "thoughts10"}
    )

    page = response.content.decode()
    assert response.status_code == HTTPStatus.OK
    assert "Discount (THOUGHTS10, 10%)" in page
    assert "−$70.00" in page
    assert 'id="checkout-total" hx-swap-oob="true">$629.98' in page
    assert "<html" not in page  # a partial, never base.html


def test_the_preview_explains_a_rejected_code(shopper):
    response = shopper.post(reverse("orders:discount_preview"), {"discount_code": "X"})

    page = response.content.decode()
    assert "We don&#x27;t recognize that discount code." in page
    assert "$699.98" in page


def test_the_preview_requires_login(client, db):
    response = client.post(reverse("orders:discount_preview"), {"discount_code": "X"})

    assert response.status_code == HTTPStatus.FOUND


def test_checking_out_with_a_code_places_a_discounted_order(shopper, order_wide_code):
    response = shopper.post(
        reverse("orders:checkout"), {**VALID_DATA, "discount_code": "thoughts10"}
    )

    order = Order.objects.get()
    assert response.status_code == HTTPStatus.FOUND
    assert order.total == Decimal("629.98")
    assert order.discount_code == "THOUGHTS10"


def test_a_rejected_code_re_renders_checkout_with_the_reason(shopper, product_code):
    product_code.expires_at = timezone.now() - timedelta(days=1)
    product_code.save()

    response = shopper.post(
        reverse("orders:checkout"), {**VALID_DATA, "discount_code": "HUB20"}
    )

    assert response.status_code == HTTPStatus.OK
    assert "That discount code has expired." in response.content.decode()
    assert not Order.objects.exists()


def test_a_code_that_goes_bad_after_validation_re_renders_checkout(
    shopper, order_wide_code, monkeypatch
):
    """The race: the form passed, then place_order's re-check failed."""

    def retired_meanwhile(*args, **kwargs):
        raise InvalidDiscountCode("That discount code is no longer active.")

    monkeypatch.setattr("orders.views.place_order", retired_meanwhile)

    response = shopper.post(
        reverse("orders:checkout"), {**VALID_DATA, "discount_code": "THOUGHTS10"}
    )

    assert response.status_code == HTTPStatus.OK
    assert "no longer active" in response.content.decode()


def test_order_pages_show_the_discount_as_granted(shopper, order_wide_code):
    shopper.post(
        reverse("orders:checkout"), {**VALID_DATA, "discount_code": "THOUGHTS10"}
    )
    order = Order.objects.get()
    order_wide_code.percent = 50
    order_wide_code.save()

    for url in [
        reverse("orders:confirmation", kwargs={"pk": order.pk}),
        reverse("orders:detail", kwargs={"pk": order.pk}),
    ]:
        page = shopper.get(url).content.decode()
        assert "Discount (THOUGHTS10, 10%)" in page
        assert "−$70.00" in page


# --- The back office ----------------------------------------------------------


def test_customers_cannot_manage_codes(client, customer):
    client.force_login(customer)

    response = client.get(reverse("orders:manage_discounts"))

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_the_code_list_has_a_designed_empty_state(client, staff_user):
    client.force_login(staff_user)

    page = client.get(reverse("orders:manage_discounts")).content.decode()

    assert "No discount codes yet" in page
    assert "Discount codes</a>" in page  # the tab


def test_the_code_list_badges_each_state(client, staff_user, order_wide_code):
    DiscountCode.objects.create(
        code="OLD", percent=5, expires_at=timezone.now() - timedelta(days=1)
    )
    DiscountCode.objects.create(code="GONE", percent=5, is_active=False)
    client.force_login(staff_user)

    page = client.get(reverse("orders:manage_discounts")).content.decode()

    for badge in ["Active", "Expired", "Retired", "Whole order"]:
        assert badge in page


def test_staff_create_a_product_code(client, staff_user, product):
    client.force_login(staff_user)

    response = client.post(
        reverse("orders:manage_discount_create"),
        {"code": "hub20", "percent": "20", "products": [product.pk], "is_active": "on"},
    )

    assert response.status_code == HTTPStatus.FOUND
    code = DiscountCode.objects.get()
    assert code.code == "HUB20"
    assert list(code.products.all()) == [product]


def test_codes_are_unique_regardless_of_case(client, staff_user, order_wide_code):
    client.force_login(staff_user)

    response = client.post(
        reverse("orders:manage_discount_create"),
        {"code": "thoughts10", "percent": "15", "is_active": "on"},
    )

    assert response.status_code == HTTPStatus.OK
    assert "already exists" in response.content.decode()
    assert DiscountCode.objects.count() == 1


def test_staff_retire_a_code_by_unticking_active(client, staff_user, order_wide_code):
    client.force_login(staff_user)

    client.post(
        reverse("orders:manage_discount_update", kwargs={"pk": order_wide_code.pk}),
        {"code": "THOUGHTS10", "percent": "10"},
    )

    order_wide_code.refresh_from_db()
    assert order_wide_code.status == DiscountCode.Status.RETIRED


def test_there_is_no_delete_screen():
    with pytest.raises(NoReverseMatch):
        reverse("orders:manage_discount_delete", kwargs={"pk": 1})
