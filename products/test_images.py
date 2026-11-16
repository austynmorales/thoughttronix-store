"""Product images: display, the model-level rules, processing, and cleanup.

Every test that saves an image uses the ``media_root`` fixture, so nothing
is ever written to the real ``media/`` directory.
"""

import re
from http import HTTPStatus
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.urls import reverse
from PIL import ExifTags, Image

from .models import Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    admin = get_user_model().objects.create_superuser(
        username="admin", password="admin123"
    )
    client.force_login(admin)
    return client


def admin_product_data(product, **overrides):
    """The Django admin's change form for ``product``, as POST data."""
    data = {
        "name": product.name,
        "slug": product.slug,
        "tagline": product.tagline,
        "description": product.description,
        "price": str(product.price),
        "is_available": "on",
        "category": str(product.category.pk),
    }
    data.update(overrides)
    return data


# --- Display -----------------------------------------------------------------


def test_display_image_url_falls_back_to_category_placeholder(product):
    assert (
        product.display_image_url == "/static/images/placeholders/home-assistants.svg"
    )


def test_display_image_url_uses_uploaded_image(product, media_root, make_image):
    product.image = make_image()
    product.save()

    assert product.display_image_url.startswith("/media/products/seraphine-home-hub-")
    assert product.display_image_url.endswith(".webp")


def test_catalog_card_shows_uploaded_image(client, product, media_root, make_image):
    product.image = make_image()
    product.save()

    response = client.get(reverse("products:catalog"))

    assert f'src="{product.image.url}"' in response.content.decode()


PLACEHOLDER_FALLBACK = (
    'onerror="this.onerror=null; '
    "this.src='/static/images/placeholders/home-assistants.svg'\""
)


def test_catalog_images_are_lazy_framed_and_fall_back(
    client, product, media_root, make_image
):
    product.image = make_image()
    product.save()

    page = client.get(reverse("products:catalog")).content.decode()

    assert PLACEHOLDER_FALLBACK in page
    assert 'loading="lazy"' in page
    assert "aspect-[4/5]" in page
    assert 'width="800"' in page and 'height="1000"' in page
    assert f'alt="{product.name}"' in page


def test_the_detail_image_loads_eagerly_and_falls_back(client, product):
    page = client.get(product.get_absolute_url()).content.decode()

    assert PLACEHOLDER_FALLBACK in page
    assert 'src="/static/images/placeholders/home-assistants.svg"' in page
    assert "aspect-[4/5]" in page
    assert 'loading="lazy"' not in page


# --- The rules live on the model field ---------------------------------------


def test_the_django_admin_rejects_an_invalid_upload(
    admin_client, product, media_root, make_image
):
    url = reverse("admin:products_product_change", args=[product.pk])

    response = admin_client.post(
        url, admin_product_data(product, image=make_image(500, 400))
    )

    assert response.status_code == HTTPStatus.OK  # re-rendered, not redirected
    assert "Images must be at least 800 pixels" in response.content.decode()
    product.refresh_from_db()
    assert not product.image


def test_full_clean_rejects_an_invalid_image(product, media_root, make_image):
    product.image = make_image(format="GIF")

    with pytest.raises(ValidationError) as excinfo:
        product.full_clean()

    assert "Unsupported image format (GIF)" in str(excinfo.value)


def test_a_stored_image_is_not_revalidated(product, media_root, make_image):
    """Editing a price never re-reads the photo — even if its file is gone."""
    product.image = make_image()
    product.save()
    product.image.storage.delete(product.image.name)
    product.refresh_from_db()

    product.price = "1.00"
    product.full_clean()  # no ValidationError, no FileNotFoundError


# --- Processing --------------------------------------------------------------


def stored_image(product):
    """Open the product's stored file with Pillow, fully loaded."""
    with product.image.storage.open(product.image.name) as file:
        image = Image.open(file)
        image.load()
    return image


def test_a_stored_image_is_webp_under_a_fresh_name(product, media_root, make_image):
    product.image = make_image(format="JPEG", name="holiday photo.jpg")
    product.save()

    assert re.fullmatch(
        r"products/seraphine-home-hub-[0-9a-f]{16}\.webp", product.image.name
    )
    assert stored_image(product).format == "WEBP"


def test_a_large_image_shrinks_to_1200_px_on_its_longest_side(
    product, media_root, make_image
):
    product.image = make_image(3000, 2000)
    product.save()

    assert stored_image(product).size == (1200, 800)


def test_a_small_image_is_not_upscaled(product, media_root, make_image):
    product.image = make_image(1000, 900)
    product.save()

    assert stored_image(product).size == (1000, 900)


def test_exif_orientation_is_applied_and_metadata_stripped(
    product, media_root, make_image
):
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6  # "rotate 90° clockwise to display"
    exif[ExifTags.Base.Make] = "Kitchen Camera Co."
    product.image = make_image(1600, 1000, format="JPEG", exif=exif)
    product.save()

    image = stored_image(product)
    assert image.size == (750, 1200)  # stood upright, then shrunk
    assert not image.getexif()
    assert "exif" not in image.info


def test_transparency_is_preserved(product, media_root, make_image):
    product.image = make_image(1000, 1000, mode="RGBA")
    product.save()

    assert stored_image(product).mode == "RGBA"


def test_an_opaque_image_has_no_alpha_channel(product, media_root, make_image):
    product.image = make_image(1000, 1000, format="JPEG")
    product.save()

    assert stored_image(product).mode == "RGB"


def test_an_animated_image_keeps_only_its_first_frame(product, media_root):
    frames = [Image.new("RGB", (1000, 1000), color) for color in ("red", "blue")]
    buffer = BytesIO()
    frames[0].save(buffer, format="WEBP", save_all=True, append_images=frames[1:])
    product.image = SimpleUploadedFile("animated.webp", buffer.getvalue())
    product.save()

    image = stored_image(product)
    assert getattr(image, "n_frames", 1) == 1
    assert image.getpixel((0, 0))[0] > 200  # red, the first frame


def test_saving_without_a_new_image_does_not_reprocess(product, media_root, make_image):
    product.image = make_image()
    product.save()
    name = product.image.name

    product.price = "1.00"
    product.save()
    product.refresh_from_db()

    assert product.image.name == name
    assert product.image.storage.exists(name)


# --- Cleanup -----------------------------------------------------------------


def test_replacing_an_image_deletes_the_old_file_after_commit(
    product, media_root, make_image, django_capture_on_commit_callbacks
):
    product.image = make_image()
    product.save()
    old_name = product.image.name
    storage = product.image.storage

    product.image = make_image()
    with django_capture_on_commit_callbacks(execute=True):
        product.save()

    assert not storage.exists(old_name)
    assert storage.exists(product.image.name)


def test_clearing_an_image_deletes_the_file_after_commit(
    product, media_root, make_image, django_capture_on_commit_callbacks
):
    product.image = make_image()
    product.save()
    old_name = product.image.name
    storage = product.image.storage

    product.image = None
    with django_capture_on_commit_callbacks(execute=True):
        product.save()

    assert not storage.exists(old_name)
    assert product.display_image_url.startswith("/static/")


def test_deleting_a_product_deletes_its_file_after_commit(
    product, media_root, make_image, django_capture_on_commit_callbacks
):
    product.image = make_image()
    product.save()
    name = product.image.name
    storage = product.image.storage

    with django_capture_on_commit_callbacks(execute=True):
        Product.objects.filter(pk=product.pk).delete()  # a queryset delete

    assert not storage.exists(name)


def test_a_rolled_back_save_deletes_nothing(
    product, media_root, make_image, django_capture_on_commit_callbacks
):
    product.image = make_image()
    product.save()
    old_name = product.image.name
    storage = product.image.storage

    with django_capture_on_commit_callbacks() as callbacks:
        with pytest.raises(RuntimeError), transaction.atomic():
            product.image = make_image()
            product.save()
            raise RuntimeError("something later in the request failed")

    assert callbacks == []
    assert storage.exists(old_name)
