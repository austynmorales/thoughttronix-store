import secrets
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.templatetags.static import static
from django.urls import reverse
from PIL import Image, ImageOps

from .validators import (
    validate_image_file_size,
    validate_image_format,
    validate_image_megapixels,
    validate_image_min_size,
)

# Categories with a dedicated placeholder illustration; anything else
# falls back to default.svg. Placeholders are static files chosen by
# category, shown when a product has no uploaded image.
PLACEHOLDER_CATEGORIES = {
    "home-assistants",
    "neural-implants",
    "neural-wearables",
    "accessories",
    "defense",
    "legacy-products",
}


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("products:category", kwargs={"slug": self.slug})

    @property
    def placeholder_image(self):
        """Static path of the placeholder image shown for this category's products."""
        if self.slug in PLACEHOLDER_CATEGORIES:
            return f"images/placeholders/{self.slug}.svg"
        return "images/placeholders/default.svg"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


MAX_IMAGE_SIDE = 1200


def product_image_path(instance, filename):
    """Storage path for a product image: ``products/<slug>-<token>.webp``.

    Every upload gets a never-before-used name, so a replaced image is a new
    URL (no stale browser caches) and the old file can be deleted without
    colliding with its replacement. The slug is truncated so the path always
    fits the field's 255-character column.
    """
    return f"products/{instance.slug[:100]}-{secrets.token_hex(8)}.webp"


class ProductQuerySet(models.QuerySet):
    def available(self):
        return self.filter(is_available=True)

    def search(self, text):
        """Simple icontains search over name and description."""
        return self.filter(
            models.Q(name__icontains=text) | models.Q(description__icontains=text)
        )


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="products")
    image = models.ImageField(
        upload_to=product_image_path,
        blank=True,
        max_length=255,
        validators=[
            validate_image_format,
            validate_image_file_size,
            validate_image_megapixels,
            validate_image_min_size,
        ],
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Normalize a newly assigned image, then delete the file it replaced.

        A new upload is one not yet committed to storage; an untouched image
        is never reprocessed, so editing a price leaves the photo alone. The
        replaced (or cleared) file is deleted only once the transaction
        commits, so a rolled-back save never removes a file still in use.
        """
        if self.image and not self.image._committed:
            self.normalize_image()

        previous_name = None
        if self.pk:
            previous_name = (
                Product.objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
            )

        super().save(*args, **kwargs)

        if previous_name and previous_name != self.image.name:
            _delete_file_on_commit(self.image.storage, previous_name)

    def get_absolute_url(self):
        return reverse("products:detail", kwargs={"slug": self.slug})

    def normalize_image(self):
        """Replace the assigned upload with a normalized WebP.

        Applies EXIF orientation, keeps only the first frame, shrinks to at
        most 1200 px on the longest side (never upscaling), preserves
        transparency, and drops all metadata — EXIF, GPS, XMP, and colour
        profiles — by encoding a fresh image with an empty ``info``.
        Only the processed file is stored; the original is discarded.
        """
        self.image.seek(0)
        with Image.open(self.image) as source:
            # exif_transpose returns an upright copy of the first frame only.
            image = ImageOps.exif_transpose(source)
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        image.info = {}

        buffer = BytesIO()
        image.save(buffer, format="WEBP", quality=85)
        # The name is ignored: upload_to generates products/<slug>-<token>.webp.
        self.image = ContentFile(buffer.getvalue(), name="image.webp")

    @property
    def display_image_url(self):
        """URL of the uploaded image, or the category placeholder if there is none."""
        if self.image:
            return self.image.url
        return static(self.category.placeholder_image)


def _delete_file_on_commit(storage, name):
    """Delete a stored file once the current transaction commits."""
    transaction.on_commit(lambda: storage.delete(name))


@receiver(post_delete, sender=Product)
def delete_product_image_file(sender, instance, **kwargs):
    """Delete a deleted product's image file once the deletion commits.

    A signal rather than a ``delete()`` override, because queryset deletes —
    the admin's bulk delete, ``seed``'s wipe — never call ``Model.delete()``.
    """
    if instance.image:
        _delete_file_on_commit(instance.image.storage, instance.image.name)
