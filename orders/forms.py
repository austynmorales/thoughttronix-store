"""The checkout form — the codebase's showcase of declarative validation.

Every rule is visible at its field declaration, in the style of data
annotations: field types validate (``EmailField``), field arguments
validate (``required``, ``max_length``, ``ChoiceField``), and the
``validators=[...]`` list carries the rest. No ``clean_*`` methods
and no ``clean()`` — none of its current rules need imperative validation.
Even the discount code, which must be checked against the cart, is a
validator: the form builds it from the cart it is given.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from products.forms import StyledModelForm

from .models import (
    US_STATES,
    Address,
    DiscountCode,
    InvalidDiscountCode,
    Order,
)
from .validators import validate_card_number, validate_expiry, zip_validator

cvv_validator = RegexValidator(r"^\d{3,4}$", "Enter the 3- or 4-digit CVV.")


class DiscountCodeField(forms.CharField):
    """A code field that cleans to the stored form: trimmed, uppercased."""

    def to_python(self, value):
        return DiscountCode.normalize(super().to_python(value))


class RedeemableCodeValidator:
    """Reject a discount code that can't be used on ``products`` right now.

    The rules themselves live in ``DiscountCode.objects.redeem`` — the
    same call ``place_order`` makes — so the form and the service can't
    disagree.
    """

    def __init__(self, products):
        self.products = list(products)

    def __call__(self, value):
        try:
            DiscountCode.objects.redeem(value, self.products)
        except InvalidDiscountCode as error:
            raise ValidationError(str(error), code="discount_code") from None


class CheckoutForm(forms.Form):
    """One page, one POST: contact, shipping, billing, payment."""

    email = forms.EmailField(label="Email")

    shipping_name = forms.CharField(label="Full name", max_length=100)
    shipping_street = forms.CharField(label="Street address", max_length=200)
    shipping_line2 = forms.CharField(
        label="Apt, suite, etc. (optional)", max_length=200, required=False
    )
    shipping_city = forms.CharField(label="City", max_length=100)
    shipping_state = forms.ChoiceField(label="State", choices=US_STATES)
    shipping_zip = forms.CharField(
        label="ZIP code", max_length=10, validators=[zip_validator]
    )
    save_shipping_address = forms.BooleanField(
        label="Save this shipping address", required=False
    )

    billing_name = forms.CharField(label="Full name", max_length=100)
    billing_street = forms.CharField(label="Street address", max_length=200)
    billing_line2 = forms.CharField(
        label="Apt, suite, etc. (optional)", max_length=200, required=False
    )
    billing_city = forms.CharField(label="City", max_length=100)
    billing_state = forms.ChoiceField(label="State", choices=US_STATES)
    billing_zip = forms.CharField(
        label="ZIP code", max_length=10, validators=[zip_validator]
    )
    save_billing_address = forms.BooleanField(
        label="Save this billing address", required=False
    )

    card_number = forms.CharField(
        label="Card number", max_length=23, validators=[validate_card_number]
    )
    card_expiry = forms.CharField(
        label="Expiry (MM/YY)", max_length=5, validators=[validate_expiry]
    )
    card_cvv = forms.CharField(label="CVV", max_length=4, validators=[cvv_validator])

    discount_code = DiscountCodeField(
        label="Discount code", max_length=30, required=False
    )

    def __init__(self, *args, cart=None, **kwargs):
        """``cart`` is what a discount code must apply to; without one
        (e.g. the address-fields partial), the code field goes unchecked."""
        super().__init__(*args, **kwargs)
        if cart is not None:
            self.fields["discount_code"].validators.append(
                RedeemableCodeValidator(line.product for line in cart.lines())
            )
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "checkbox checkbox-primary"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "select w-full"
            else:
                widget.attrs["class"] = "input w-full"

    # Field groups for the template — the form owns its own structure.

    def shipping_fields(self):
        return [self[name] for name in self.fields if name.startswith("shipping_")]

    def billing_fields(self):
        return [self[name] for name in self.fields if name.startswith("billing_")]

    def card_fields(self):
        return [self[name] for name in self.fields if name.startswith("card_")]


class AddressForm(StyledModelForm):
    """Add or edit a saved address — the model carries every rule.

    Ticking a default checkbox moves that default here; ``Address.save``
    clears it from the customer's other addresses.
    """

    class Meta:
        model = Address
        fields = [*Address.FIELDS, "is_default_shipping", "is_default_billing"]


class DiscountCodeForm(StyledModelForm):
    """Create or edit a discount code in the back office.

    The code is uppercased before the uniqueness check, so ``thoughts10``
    collides with an existing ``THOUGHTS10`` as it should.
    """

    code = DiscountCodeField(
        max_length=30, help_text=DiscountCode._meta.get_field("code").help_text
    )

    class Meta:
        model = DiscountCode
        fields = ["code", "percent", "products", "expires_at", "is_active"]
        widgets = {
            "expires_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["products"].queryset = self.fields["products"].queryset.order_by(
            "name"
        )


class OrderStatusForm(forms.ModelForm):
    """The back-office status dropdown — any of the four states, anytime.

    Guarding the workflow (no un-cancelling, no re-shipping a delivered
    order) is deliberately left as a student exercise.
    """

    class Meta:
        model = Order
        fields = ["status"]
        widgets = {"status": forms.Select(attrs={"class": "select"})}
