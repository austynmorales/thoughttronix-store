"""Back-office catalog management: access control, CRUD round-trips, validation."""

from decimal import Decimal
from http import HTTPStatus

import pytest
from django.urls import reverse

from .models import Category, Product, Tag

pytestmark = pytest.mark.django_db


def manage_urls(product, tag):
    """Every staff-only catalog URL, for the access-control sweeps."""
    return [
        reverse("products:manage_products"),
        reverse("products:manage_product_create"),
        reverse("products:manage_product_update", kwargs={"pk": product.pk}),
        reverse("products:manage_product_delete", kwargs={"pk": product.pk}),
        reverse("products:manage_catalog"),
        reverse("products:manage_category_create"),
        reverse("products:manage_category_update", kwargs={"pk": product.category.pk}),
        reverse("products:manage_tag_create"),
        reverse("products:manage_tag_update", kwargs={"pk": tag.pk}),
    ]


def product_data(category, **overrides):
    data = {
        "name": "MindSync Sleep Halo",
        "slug": "mindsync-sleep-halo",
        "tagline": "Dream in someone else's 4K.",
        "description": "A bedside accessory for the MindSync line.",
        "price": "199.99",
        "is_available": "on",
        "category": str(category.pk),
    }
    data.update(overrides)
    return data


# --- Access control ----------------------------------------------------------


def test_anonymous_users_are_sent_to_login(client, product, tag):
    for url in manage_urls(product, tag):
        response = client.get(url)

        assert response.status_code == HTTPStatus.FOUND, url
        assert reverse("accounts:login") in response.url


def test_customers_get_403(client, customer, product, tag):
    client.force_login(customer)

    for url in manage_urls(product, tag):
        assert client.get(url).status_code == HTTPStatus.FORBIDDEN, url


def test_staff_get_200(client, staff_user, product, tag):
    client.force_login(staff_user)

    for url in manage_urls(product, tag):
        response = client.get(url)

        assert response.status_code == HTTPStatus.OK, url
        # A multi-line {# #} comment renders as literal text — guard
        # against template comments leaking onto the page.
        assert "{#" not in response.content.decode(), url


def test_navbar_shows_back_office_to_staff_only(client, staff_user, customer):
    client.force_login(staff_user)
    assert "Back office" in client.get(reverse("products:catalog")).content.decode()

    client.force_login(customer)
    assert "Back office" not in client.get(reverse("products:catalog")).content.decode()


# --- Product CRUD ------------------------------------------------------------


def test_staff_can_create_a_product(client, staff_user, category, tag):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"),
        product_data(category, tags=[str(tag.pk)]),
        follow=True,
    )

    product = Product.objects.get(slug="mindsync-sleep-halo")
    assert product.price == Decimal("199.99")
    assert product.category == category
    assert list(product.tags.all()) == [tag]
    assert "created." in response.content.decode()


def test_staff_can_edit_a_price(client, staff_user, product):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["price"] = "299.99"

    client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    product.refresh_from_db()
    assert product.price == Decimal("299.99")


def test_staff_can_mark_a_product_unavailable(client, staff_user, product):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    del data["is_available"]  # an unchecked checkbox is simply absent

    client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    product.refresh_from_db()
    assert not product.is_available


def test_staff_can_delete_a_product(client, staff_user, product):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_delete", kwargs={"pk": product.pk})
    )

    assert response.url == reverse("products:manage_products")
    assert not Product.objects.exists()


def test_manage_list_shows_unavailable_products(
    client, staff_user, unavailable_product
):
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_products")).content.decode()

    assert unavailable_product.name in page
    assert "Unavailable" in page


# --- Form validation ---------------------------------------------------------


def test_price_must_be_positive(client, staff_user, category):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"),
        product_data(category, price="-12.00"),
    )

    assert response.status_code == HTTPStatus.OK
    assert "greater than or equal to 0.01" in response.content.decode()
    assert not Product.objects.exists()


def test_slug_must_be_unique(client, staff_user, product):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"),
        product_data(product.category, slug=product.slug),
    )

    assert response.status_code == HTTPStatus.OK
    assert "already exists" in response.content.decode()
    assert Product.objects.count() == 1


def test_name_is_required(client, staff_user, category):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"), product_data(category, name="")
    )

    assert response.status_code == HTTPStatus.OK
    assert "This field is required." in response.content.decode()
    assert not Product.objects.exists()


# --- Product images ----------------------------------------------------------


def update_url(product):
    return reverse("products:manage_product_update", kwargs={"pk": product.pk})


def test_the_product_form_is_multipart_and_states_the_rules(
    client, staff_user, product
):
    client.force_login(staff_user)

    page = client.get(update_url(product)).content.decode()

    assert 'enctype="multipart/form-data"' in page
    assert 'class="file-input w-full"' in page
    assert "at least 800 pixels on the shortest side" in page
    # The preview shows the placeholder; nothing to remove yet.
    assert "/static/images/placeholders/home-assistants.svg" in page
    assert "Remove image" not in page


def test_staff_can_upload_an_image(client, staff_user, product, media_root, make_image):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)

    response = client.post(update_url(product), {**data, "image": make_image()})

    assert response.status_code == HTTPStatus.FOUND
    product.refresh_from_db()
    assert product.image.name.endswith(".webp")


def test_an_invalid_upload_rerenders_with_the_error_and_input_kept(
    client, staff_user, product, media_root, make_image
):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["price"] = "299.99"

    response = client.post(update_url(product), {**data, "image": make_image(500, 400)})

    assert response.status_code == HTTPStatus.OK
    page = response.content.decode()
    assert "This image is 500×400 pixels." in page
    assert 'value="299.99"' in page  # the other edit survives
    # The preview still shows what's stored, not the rejected upload.
    assert "/static/images/placeholders/home-assistants.svg" in page
    product.refresh_from_db()
    assert not product.image
    assert product.price == Decimal("349.99")


def test_staff_can_remove_an_image(client, staff_user, product, media_root, make_image):
    product.image = make_image()
    product.save()
    client.force_login(staff_user)
    assert "Remove image" in client.get(update_url(product)).content.decode()

    data = product_data(product.category, name=product.name, slug=product.slug)
    client.post(update_url(product), {**data, "remove_image": "on"})

    product.refresh_from_db()
    assert not product.image


def test_uploading_and_removing_at_once_is_rejected(
    client, staff_user, product, media_root, make_image
):
    product.image = make_image()
    product.save()
    stored = product.image.name
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)

    response = client.post(
        update_url(product), {**data, "image": make_image(), "remove_image": "on"}
    )

    assert "not both" in response.content.decode()
    product.refresh_from_db()
    assert product.image.name == stored


def test_editing_without_a_file_keeps_the_image(
    client, staff_user, product, media_root, make_image
):
    product.image = make_image()
    product.save()
    stored = product.image.name
    client.force_login(staff_user)

    data = product_data(product.category, name=product.name, slug=product.slug)
    client.post(update_url(product), {**data, "price": "1.00"})

    product.refresh_from_db()
    assert product.image.name == stored
    assert product.price == Decimal("1.00")


def test_the_product_list_shows_lazy_thumbnails(
    client, staff_user, product, media_root, make_image
):
    product.image = make_image()
    product.save()
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_products")).content.decode()

    assert f'src="{product.image.url}"' in page
    assert 'loading="lazy"' in page


# --- Categories and tags -----------------------------------------------------


def test_staff_can_create_and_edit_a_category(client, staff_user):
    client.force_login(staff_user)

    client.post(
        reverse("products:manage_category_create"),
        {"name": "Defense", "slug": "defense"},
    )
    category = Category.objects.get(slug="defense")

    client.post(
        reverse("products:manage_category_update", kwargs={"pk": category.pk}),
        {"name": "Home Defense", "slug": "defense"},
    )

    category.refresh_from_db()
    assert category.name == "Home Defense"


def test_staff_can_create_and_edit_a_tag(client, staff_user):
    client.force_login(staff_user)

    client.post(
        reverse("products:manage_tag_create"),
        {"name": "new arrival", "slug": "new-arrival"},
    )
    tag = Tag.objects.get(slug="new-arrival")

    client.post(
        reverse("products:manage_tag_update", kwargs={"pk": tag.pk}),
        {"name": "just landed", "slug": "new-arrival"},
    )

    tag.refresh_from_db()
    assert tag.name == "just landed"


def test_manage_catalog_lists_categories_and_tags(client, staff_user, product, tag):
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_catalog")).content.decode()

    assert product.category.name in page
    assert tag.name in page
