"""Unit tests for the product image validators — no database.

Coverage priority 1 in the image PRD: each rule accepts a valid image and
rejects an invalid one with its specific message.
"""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from .validators import (
    validate_image_file_size,
    validate_image_format,
    validate_image_megapixels,
    validate_image_min_size,
)

ALL_VALIDATORS = [
    validate_image_format,
    validate_image_file_size,
    validate_image_megapixels,
    validate_image_min_size,
]


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_every_rule_accepts_a_valid_image(make_image, image_format):
    upload = make_image(1000, 800, format=image_format)

    for validator in ALL_VALIDATORS:
        validator(upload)  # no ValidationError


# --- validate_image_format ---------------------------------------------------


def test_rejects_a_gif_renamed_png(make_image):
    upload = make_image(format="GIF", name="sneaky.png")

    with pytest.raises(ValidationError) as excinfo:
        validate_image_format(upload)

    assert excinfo.value.messages == [
        "Unsupported image format (GIF). Upload a JPEG, PNG, or WebP file."
    ]


def test_rejects_a_file_that_is_not_an_image():
    upload = SimpleUploadedFile("notes.png", b"definitely not pixels")

    with pytest.raises(ValidationError) as excinfo:
        validate_image_format(upload)

    assert "Upload a valid image" in excinfo.value.messages[0]


def test_dimension_rules_leave_unreadable_files_to_the_format_rule():
    upload = SimpleUploadedFile("notes.png", b"definitely not pixels")

    validate_image_megapixels(upload)
    validate_image_min_size(upload)


# --- validate_image_file_size ------------------------------------------------


def test_rejects_a_file_over_10_mb(make_image):
    png = make_image().read()
    padding = b"\0" * (int(14.2 * 1024 * 1024) - len(png))
    upload = SimpleUploadedFile("huge.png", png + padding)

    with pytest.raises(ValidationError) as excinfo:
        validate_image_file_size(upload)

    assert excinfo.value.messages == ["This file is 14.2 MB. The maximum is 10 MB."]


def test_accepts_a_file_of_exactly_10_mb(make_image):
    png = make_image().read()
    upload = SimpleUploadedFile("big.png", png + b"\0" * (10 * 1024 * 1024 - len(png)))

    validate_image_file_size(upload)


# --- validate_image_megapixels -----------------------------------------------


def test_rejects_an_image_over_50_megapixels(make_image):
    # 1-bit mode keeps the in-memory test image small.
    upload = make_image(9000, 6000, mode="1")

    with pytest.raises(ValidationError) as excinfo:
        validate_image_megapixels(upload)

    assert excinfo.value.messages == [
        "This image is 9000×6000 pixels. The maximum is 50 megapixels."
    ]


def test_rejects_a_decompression_bomb_without_decoding_it(make_image):
    # Over Pillow's own ~179 MP guard, so Image.open refuses the header.
    upload = make_image(15000, 13000, mode="1")

    with pytest.raises(ValidationError) as excinfo:
        validate_image_megapixels(upload)

    assert excinfo.value.messages == [
        "This image has far too many pixels. The maximum is 50 megapixels."
    ]
    # The other rules stay quiet, so the employee sees one message, not three.
    validate_image_format(upload)
    validate_image_min_size(upload)


# --- validate_image_min_size -------------------------------------------------


def test_rejects_an_image_under_800_px_on_its_shortest_side(make_image):
    upload = make_image(500, 400)

    with pytest.raises(ValidationError) as excinfo:
        validate_image_min_size(upload)

    assert excinfo.value.messages == [
        "This image is 500×400 pixels. Images must be at least 800 pixels on "
        "their shortest side."
    ]


def test_accepts_exactly_800_px_on_the_shortest_side(make_image):
    validate_image_min_size(make_image(2000, 800))
