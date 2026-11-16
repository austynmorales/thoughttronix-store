"""Back-office forms for the catalog models.

ModelForms inherit the models' own rules (name required, slug unique,
the image upload rules); the explicit ``price`` declaration adds the one
rule the model doesn't carry — the price must be positive. Widgets get
their DaisyUI classes in one shared ``__init__`` loop, as on
``CheckoutForm``.
"""

import copy
from decimal import Decimal

from django import forms

from .models import Category, Product, Tag


class StyledModelForm(forms.ModelForm):
    """Base form that dresses every widget in DaisyUI classes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "toggle toggle-primary"
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = "textarea w-full"
                widget.attrs.setdefault("rows", 6)
            elif isinstance(widget, forms.SelectMultiple):
                widget.attrs["class"] = "select h-auto w-full"
                widget.attrs.setdefault("size", 8)
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "select w-full"
            elif isinstance(widget, forms.FileInput):
                widget.attrs["class"] = "file-input w-full"
            else:
                widget.attrs["class"] = "input w-full"


class ProductForm(StyledModelForm):
    price = forms.DecimalField(
        label="Price (USD)",
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    remove_image = forms.BooleanField(
        required=False,
        label="Remove image",
        help_text="Return this product to its category placeholder.",
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "tagline",
            "description",
            "price",
            "category",
            "tags",
            "image",
            "is_available",
            "is_featured",
        ]
        widgets = {
            # A plain file input: the preview and "Remove image" toggle are
            # laid out by the form template instead of Django's clearable widget.
            "image": forms.FileInput(
                attrs={"accept": "image/jpeg,image/png,image/webp"}
            ),
        }
        help_texts = {
            "image": (
                "JPEG, PNG, or WebP · up to 10 MB · at least 800 pixels on the "
                "shortest side."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The preview shows the image as stored. Validation assigns the
        # upload to ``self.instance`` — even a rejected one — so the preview
        # works from its own copy, taken before any of that happens.
        self.preview_product = None
        if self.instance.pk:
            self.preview_product = copy.copy(self.instance)
            self.preview_product.image = self.instance.image.name

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("remove_image"):
            if self.files.get(self.add_prefix("image")):
                self.add_error(
                    "remove_image",
                    "Upload a new image or tick “Remove image”, not both.",
                )
            else:
                cleaned_data["image"] = False  # FileField's "clear" signal
        return cleaned_data


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug"]


class TagForm(StyledModelForm):
    class Meta:
        model = Tag
        fields = ["name", "slug"]
