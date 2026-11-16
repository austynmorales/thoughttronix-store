"""Product image validators — small, pure, and unit-testable.

Plain functions that raise ``ValidationError``, wired in through
``Product.image``'s ``validators=[...]`` so the Django admin, the
back-office form, and ``seed`` (via ``full_clean()``) all enforce the same
rules. Each message names the problem and how to fix it.

Every rule checks only a *new* upload. An image already in storage passed
these checks when it arrived, so editing a product's price never re-reads
its photo — and never fails because a stored file went missing.
"""

import warnings

from django.core.exceptions import ValidationError
from PIL import Image

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 50_000_000
MIN_SHORTEST_SIDE = 800

INVALID_IMAGE_MESSAGE = (
    "Upload a valid image. The file you uploaded was either not an image "
    "or a corrupted image."
)


def _is_new_upload(value) -> bool:
    """True unless ``value`` is a ``FieldFile`` already saved to storage."""
    return not getattr(value, "_committed", False)


class _TooManyPixels(Exception):
    """Pillow refused to even open the header: a near-certain decompression bomb."""


def _read_header(value) -> tuple[str, tuple[int, int]] | None:
    """Return ``(format, (width, height))`` read from the file's header.

    ``Image.open`` reads only the header — pixels are not decoded — so this
    is safe to call on a decompression bomb. Returns ``None`` if Pillow
    cannot identify the file as an image at all, and raises
    ``_TooManyPixels`` if Pillow's own bomb guard (~179 MP) refuses it.
    """
    value.seek(0)
    try:
        with warnings.catch_warnings():
            # Pillow warns above ~89 MP; our own 50 MP limit reports it instead.
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(value) as image:
                return image.format, image.size
    except Image.DecompressionBombError:
        raise _TooManyPixels from None
    except Exception:
        return None
    finally:
        value.seek(0)


def validate_image_format(value) -> None:
    """Reject anything that isn't really a JPEG, PNG, or WebP.

    The format is read from the file's contents, not its name, so a GIF
    renamed ``photo.png`` is still rejected as a GIF.
    """
    if not _is_new_upload(value):
        return
    try:
        header = _read_header(value)
    except _TooManyPixels:
        return  # validate_image_megapixels reports it.
    if header is None:
        raise ValidationError(INVALID_IMAGE_MESSAGE, code="invalid_image")
    image_format = header[0]
    if image_format not in ALLOWED_FORMATS:
        raise ValidationError(
            f"Unsupported image format ({image_format}). "
            "Upload a JPEG, PNG, or WebP file.",
            code="image_format",
        )


def validate_image_file_size(value) -> None:
    """Reject a file larger than 10 MB."""
    if not _is_new_upload(value):
        return
    if value.size > MAX_FILE_BYTES:
        megabytes = value.size / (1024 * 1024)
        raise ValidationError(
            f"This file is {megabytes:.1f} MB. The maximum is 10 MB.",
            code="image_file_size",
        )


def validate_image_megapixels(value) -> None:
    """Reject an image over 50 megapixels, judged from its header alone.

    This is the decompression-bomb guard: a tiny file can declare enormous
    dimensions, so the check happens before any pixels are decoded.
    """
    if not _is_new_upload(value):
        return
    try:
        header = _read_header(value)
    except _TooManyPixels:
        raise ValidationError(
            "This image has far too many pixels. The maximum is 50 megapixels.",
            code="image_megapixels",
        ) from None
    if header is None:
        return  # validate_image_format reports unreadable files.
    width, height = header[1]
    if width * height > MAX_PIXELS:
        raise ValidationError(
            f"This image is {width}×{height} pixels. The maximum is 50 megapixels.",
            code="image_megapixels",
        )


def validate_image_min_size(value) -> None:
    """Reject an image whose shortest side is under 800 pixels."""
    if not _is_new_upload(value):
        return
    try:
        header = _read_header(value)
    except _TooManyPixels:
        return  # validate_image_megapixels reports it.
    if header is None:
        return  # validate_image_format reports unreadable files.
    width, height = header[1]
    if min(width, height) < MIN_SHORTEST_SIDE:
        raise ValidationError(
            f"This image is {width}×{height} pixels. Images must be at least "
            "800 pixels on their shortest side.",
            code="image_min_size",
        )
