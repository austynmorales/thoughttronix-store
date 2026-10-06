"""The address book: default rules, de-duplication, owner-only views,
and the checkout picker."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from .models import Address
from .test_checkout_form import VALID_DATA

OFFICE = {
    "name": "Casey Monroe",
    "street": "77 Cortex Lane",
    "line2": "Suite 400",
    "city": "Amarillo",
    "state": "TX",
    "zip": "79101",
}


@pytest.fixture
def office(customer):
    return Address.objects.create(user=customer, **OFFICE)


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user(username="other", password="x")


@pytest.fixture
def others_address(other_customer):
    return Address.objects.create(user=other_customer, **OFFICE)


def address_fields(address):
    return {field: getattr(address, field) for field in Address.FIELDS}


# --- Model behavior ----------------------------------------------------------


def test_summary_is_one_readable_line(address, office):
    assert address.summary == "Casey Monroe — 214 Synapse Street, Canyon, TX 79015"
    assert str(office) == (
        "Casey Monroe — 77 Cortex Lane, Suite 400, Amarillo, TX 79101"
    )


def test_setting_a_default_moves_it(address, office):
    office.is_default_shipping = True
    office.save()

    address.refresh_from_db()
    assert not address.is_default_shipping
    assert address.is_default_billing  # the other kind is untouched
    assert office.is_default_shipping


def test_the_database_allows_one_default_of_each_kind(address, office):
    with pytest.raises(IntegrityError):
        # .update() bypasses Address.save — the constraint is the backstop.
        Address.objects.filter(pk=office.pk).update(is_default_shipping=True)


def test_defaults_lookup(customer, address, office):
    assert customer.addresses.default_shipping() == address
    assert customer.addresses.default_billing() == address
    address.delete()
    assert customer.addresses.default_shipping() is None


def test_save_unique_creates_and_claims_empty_slots(customer):
    address = Address.objects.save_unique(customer, as_shipping=True, **OFFICE)

    assert address.user == customer
    assert address.is_default_shipping
    assert not address.is_default_billing


def test_save_unique_reuses_an_exact_match(customer, office):
    again = Address.objects.save_unique(customer, as_billing=True, **OFFICE)

    assert again == office
    assert customer.addresses.count() == 1
    assert again.is_default_billing  # the empty billing slot was claimed


def test_save_unique_treats_an_edit_as_a_new_address(customer, office):
    Address.objects.save_unique(customer, **{**OFFICE, "line2": "Suite 401"})

    assert customer.addresses.count() == 2


def test_save_unique_never_replaces_an_existing_default(customer, address):
    new = Address.objects.save_unique(
        customer, as_shipping=True, as_billing=True, **OFFICE
    )

    assert not new.is_default_shipping
    assert not new.is_default_billing
    address.refresh_from_db()
    assert address.is_default_shipping
    assert address.is_default_billing


def test_save_unique_only_matches_the_same_customer(customer, others_address):
    mine = Address.objects.save_unique(customer, **OFFICE)

    assert mine != others_address
    assert mine.user == customer


# --- The address book pages --------------------------------------------------


def test_address_pages_require_sign_in(client):
    response = client.get(reverse("orders:addresses"))

    assert response.status_code == HTTPStatus.FOUND
    assert reverse("accounts:login") in response.url


def test_empty_address_book_shows_the_empty_state(client, customer):
    client.force_login(customer)
    response = client.get(reverse("orders:addresses"))

    assert b"No saved addresses yet" in response.content


def test_list_shows_only_my_addresses_with_default_badges(
    client, customer, address, others_address
):
    client.force_login(customer)
    response = client.get(reverse("orders:addresses"))

    assert list(response.context["addresses"]) == [address]
    assert b"Default shipping" in response.content
    assert b"Default billing" in response.content


def test_first_address_form_starts_with_both_defaults_ticked(client, customer):
    client.force_login(customer)
    form = client.get(reverse("orders:address_create")).context["form"]

    assert form.initial == {"is_default_shipping": True, "is_default_billing": True}


def test_later_address_form_leaves_filled_slots_unticked(client, customer, address):
    client.force_login(customer)
    form = client.get(reverse("orders:address_create")).context["form"]

    assert form.initial == {"is_default_shipping": False, "is_default_billing": False}


def test_creating_an_address_saves_it_to_my_book(client, customer, address):
    client.force_login(customer)
    response = client.post(
        reverse("orders:address_create"), {**OFFICE, "is_default_shipping": "on"}
    )

    assert response.status_code == HTTPStatus.FOUND
    office = customer.addresses.get(street="77 Cortex Lane")
    assert office.is_default_shipping
    address.refresh_from_db()
    assert not address.is_default_shipping  # the default moved
    assert address.is_default_billing


def test_the_address_form_validates_zip_and_state(client, customer):
    client.force_login(customer)
    response = client.post(
        reverse("orders:address_create"), {**OFFICE, "zip": "790", "state": "XX"}
    )

    assert response.status_code == HTTPStatus.OK
    assert set(response.context["form"].errors) == {"zip", "state"}
    assert not Address.objects.exists()


def test_editing_an_address(client, customer, office):
    client.force_login(customer)
    client.post(
        reverse("orders:address_update", args=[office.pk]),
        {**OFFICE, "line2": "Suite 500"},
    )

    office.refresh_from_db()
    assert office.line2 == "Suite 500"


def test_deleting_an_address(client, customer, address):
    client.force_login(customer)
    response = client.post(reverse("orders:address_delete", args=[address.pk]))

    assert response.status_code == HTTPStatus.FOUND
    assert not customer.addresses.exists()


@pytest.mark.parametrize("name", ["orders:address_update", "orders:address_delete"])
def test_another_customers_address_is_not_found(client, customer, others_address, name):
    client.force_login(customer)

    assert client.get(reverse(name, args=[others_address.pk])).status_code == 404
    assert client.post(reverse(name, args=[others_address.pk])).status_code == 404
    others_address.refresh_from_db()  # still there, unchanged


# --- Checkout ----------------------------------------------------------------


def test_checkout_starts_from_the_default_addresses(
    client, customer, cart_item, address
):
    office = Address.objects.create(user=customer, **OFFICE)
    office.is_default_billing = True
    office.save()
    client.force_login(customer)

    form = client.get(reverse("orders:checkout")).context["form"]

    assert form.initial["shipping_street"] == "214 Synapse Street"
    assert form.initial["billing_street"] == "77 Cortex Lane"
    assert form.initial["billing_line2"] == "Suite 400"


def test_checking_out_with_save_ticked_fills_the_address_book(
    client, customer, cart_item
):
    client.force_login(customer)
    response = client.post(
        reverse("orders:checkout"), {**VALID_DATA, "save_shipping_address": "on"}
    )

    assert response.status_code == HTTPStatus.FOUND
    saved = customer.addresses.get()
    assert saved.street == VALID_DATA["shipping_street"]
    assert saved.is_default_shipping
    assert not saved.is_default_billing


def test_checkout_without_saved_addresses_has_no_picker(client, customer, cart_item):
    client.force_login(customer)
    response = client.get(reverse("orders:checkout"))

    assert b"Fill from a saved address" not in response.content
    assert "shipping_street" not in response.context["form"].initial


def test_checkout_lists_my_addresses_in_the_picker(
    client, customer, cart_item, address, others_address
):
    client.force_login(customer)
    response = client.get(reverse("orders:checkout"))

    assert b"Fill from a saved address" in response.content
    assert list(response.context["addresses"]) == [address]


def test_picker_fills_a_section_from_a_saved_address(client, customer, office):
    client.force_login(customer)
    response = client.get(
        reverse("orders:address_fields"), {"section": "billing", "address": office.pk}
    )

    assert response.status_code == HTTPStatus.OK
    names = [t.name for t in response.templates]
    assert names[0] == "orders/partials/_address_fields.html"
    assert "base.html" not in names
    assert b'name="billing_street"' in response.content
    assert b'value="77 Cortex Lane"' in response.content
    assert b"shipping_street" not in response.content


@pytest.mark.parametrize(
    "params",
    [
        {"section": "payment", "address": "1"},
        {"section": "shipping", "address": "abc"},
        {"section": "shipping"},
    ],
)
def test_picker_rejects_bad_requests(client, customer, params):
    client.force_login(customer)

    assert client.get(reverse("orders:address_fields"), params).status_code == 404


def test_picker_cannot_read_another_customers_address(client, customer, others_address):
    client.force_login(customer)
    response = client.get(
        reverse("orders:address_fields"),
        {"section": "shipping", "address": others_address.pk},
    )

    assert response.status_code == 404
