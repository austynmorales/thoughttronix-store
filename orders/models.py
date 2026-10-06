from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import cached_property

from products.models import Product

from .validators import discount_code_validator, zip_validator

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

US_STATES = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("DC", "District of Columbia"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
]


class InvalidDiscountCode(ValueError):
    """A discount code that can't be used; the message is customer-facing."""


class DiscountCodeQuerySet(models.QuerySet):
    def redeem(self, text, products):
        """The code ``text`` names, provided it can be used on ``products``.

        Case and surrounding spaces don't matter. Raises
        ``InvalidDiscountCode`` saying why when the code is unknown,
        retired, expired, or covers none of ``products``.
        """
        code = self.filter(code=DiscountCode.normalize(text)).first()
        if code is None:
            raise InvalidDiscountCode("We don't recognize that discount code.")
        if code.status == DiscountCode.Status.RETIRED:
            raise InvalidDiscountCode("That discount code is no longer active.")
        if code.status == DiscountCode.Status.EXPIRED:
            raise InvalidDiscountCode("That discount code has expired.")
        if not code.applies_to(products):
            raise InvalidDiscountCode(
                "That discount code doesn't apply to anything in your cart."
            )
        return code


class DiscountCode(models.Model):
    """A percentage off, entered at checkout.

    With no ``products`` the code discounts the whole order; with some,
    only those products' lines. A code works while it is active and
    unexpired — retiring it (``is_active=False``) is reversible. Orders
    copy the code, percent, and amounts, so editing, retiring, or even
    deleting a code never touches order history.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        RETIRED = "RETIRED", "Retired"

    code = models.CharField(
        max_length=30,
        unique=True,
        validators=[discount_code_validator],
        help_text="Customers can type it in any case.",
    )
    percent = models.PositiveSmallIntegerField(
        "Percent off",
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    products = models.ManyToManyField(
        Product,
        blank=True,
        related_name="discount_codes",
        help_text="Leave empty to discount the whole order.",
    )
    expires_at = models.DateTimeField(
        "Expires at", null=True, blank=True, help_text="Leave empty to never expire."
    )
    is_active = models.BooleanField(
        "Active", default=True, help_text="Untick to retire the code."
    )

    objects = DiscountCodeQuerySet.as_manager()

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(percent__gte=1, percent__lte=100),
                name="discount_percent_1_to_100",
            )
        ]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.normalize(self.code)
        super().save(*args, **kwargs)

    @staticmethod
    def normalize(text):
        """The stored form of a typed code: trimmed and uppercased."""
        return (text or "").strip().upper()

    @property
    def status(self):
        """Retired beats expired: a switched-off code reads as retired."""
        if not self.is_active:
            return self.Status.RETIRED
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.Status.ACTIVE

    @property
    def is_order_wide(self):
        return not self._product_ids

    @cached_property
    def _product_ids(self):
        return set(self.products.values_list("pk", flat=True))

    def covers(self, product):
        """Whether this code discounts ``product``'s lines."""
        return self.is_order_wide or product.pk in self._product_ids

    def applies_to(self, products):
        """Whether this code discounts any of ``products``."""
        return any(self.covers(product) for product in products)

    def discount_on(self, product, amount):
        """Money off a line of ``product`` worth ``amount``, rounded half-up
        to the cent; zero when the code doesn't cover the product."""
        if not self.covers(product):
            return ZERO
        return (amount * self.percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)


class Cart(models.Model):
    """A customer's cart — one per user, created lazily on first touch."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )

    def __str__(self):
        return f"Cart for {self.user.username}"

    @classmethod
    def for_user(cls, user):
        """Return the user's cart, creating it on first touch."""
        cart, _ = cls.objects.get_or_create(user=user)
        return cart

    def add(self, product):
        """Add a product to the cart; a duplicate add increments its line."""
        item, created = self.items.get_or_create(product=product)
        if not created:
            item.quantity += 1
            item.save()
        return item

    def lines(self):
        """Line items with their products loaded, ready for display."""
        return self.items.select_related("product")

    def total(self):
        return sum((item.line_total for item in self.lines()), ZERO)

    def discount(self, code):
        """Money off this cart under ``code``; zero when ``code`` is ``None``."""
        if code is None:
            return ZERO
        return sum(
            (code.discount_on(item.product, item.line_total) for item in self.lines()),
            ZERO,
        )

    def item_count(self):
        """Total units across all lines — the navbar badge number."""
        return self.items.aggregate(count=models.Sum("quantity"))["count"] or 0


class CartItem(models.Model):
    """One product line in a cart; the cart–product pair is unique."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"], name="unique_cart_product"
            )
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

    @property
    def line_total(self):
        return self.product.price * self.quantity

    def increment(self):
        self.quantity += 1
        self.save()

    def decrement(self):
        """Step the quantity down, stopping at one — removal is explicit."""
        if self.quantity > 1:
            self.quantity -= 1
            self.save()


class Order(models.Model):
    """A placed order — a snapshot, never a live view of the catalog.

    Addresses are flat denormalized fields: the order must not change if
    the customer later edits anything. Of the card, only the last four
    digits survive checkout. ``total`` is what was charged — after any
    discount.
    """

    class Status(models.TextChoices):
        PLACED = "PLACED", "Placed"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PLACED
    )
    total = models.DecimalField(max_digits=10, decimal_places=2)
    email = models.EmailField()

    shipping_name = models.CharField(max_length=100)
    shipping_street = models.CharField(max_length=200)
    shipping_line2 = models.CharField(max_length=200, blank=True)
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=2)
    shipping_zip = models.CharField(max_length=10)

    billing_name = models.CharField(max_length=100)
    billing_street = models.CharField(max_length=200)
    billing_line2 = models.CharField(max_length=200, blank=True)
    billing_city = models.CharField(max_length=100)
    billing_state = models.CharField(max_length=2)
    billing_zip = models.CharField(max_length=10)

    card_last4 = models.CharField(max_length=4)

    # The discount as granted at checkout — copied, so the order is immune
    # to later edits of the code. ``discount`` is only a live link for
    # staff, and goes null if the code is ever deleted.
    discount = models.ForeignKey(
        DiscountCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    discount_code = models.CharField(max_length=30, blank=True)
    discount_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)

    # default (not auto_now_add) so the seed can backdate orders.
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def number(self):
        """The customer-facing order number, e.g. ``TT-2026-00042``."""
        return f"TT-{self.created_at.year}-{self.pk:05d}"

    @property
    def subtotal(self):
        """The order's value before its discount."""
        return self.total + self.discount_amount


class OrderItem(models.Model):
    """One line of an order, priced as of purchase time.

    Name and unit price are denormalized: order history must not change
    when the catalog does. The product FK survives for linking while the
    product exists.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    # This line's share of the order's discount; the lines sum to it exactly.
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def discounted_total(self):
        return self.line_total - self.discount_amount


class AddressQuerySet(models.QuerySet):
    def default_shipping(self):
        """The default shipping address in this queryset, or ``None``."""
        return self.filter(is_default_shipping=True).first()

    def default_billing(self):
        """The default billing address in this queryset, or ``None``."""
        return self.filter(is_default_billing=True).first()

    def save_unique(self, user, *, as_shipping=False, as_billing=False, **fields):
        """Save an address to the user's book unless an identical one exists.

        ``fields`` are the six address fields. An exact match on all of
        them is reused rather than duplicated. Either way, the address
        then claims each requested default slot the user hasn't filled —
        an existing default is never replaced.
        """
        address = self.filter(user=user, **fields).first() or Address(
            user=user, **fields
        )
        address.claim_empty_defaults(shipping=as_shipping, billing=as_billing)
        address.save()
        return address


class Address(models.Model):
    """A saved address in a customer's address book.

    Untyped — any address serves for shipping or billing. Orders copy
    the fields at checkout, so editing or deleting an address never
    touches order history. Each customer has at most one default of
    each kind; saving a new default moves it.
    """

    FIELDS = ["name", "street", "line2", "city", "state", "zip"]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    name = models.CharField("Full name", max_length=100)
    street = models.CharField("Street address", max_length=200)
    line2 = models.CharField("Apt, suite, etc. (optional)", max_length=200, blank=True)
    city = models.CharField("City", max_length=100)
    state = models.CharField("State", max_length=2, choices=US_STATES)
    zip = models.CharField("ZIP code", max_length=10, validators=[zip_validator])

    is_default_shipping = models.BooleanField("Default shipping address", default=False)
    is_default_billing = models.BooleanField("Default billing address", default=False)

    objects = AddressQuerySet.as_manager()

    class Meta:
        ordering = ["pk"]
        verbose_name_plural = "addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default_shipping=True),
                name="one_default_shipping_per_user",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default_billing=True),
                name="one_default_billing_per_user",
            ),
        ]

    def __str__(self):
        return self.summary

    def save(self, *args, **kwargs):
        """Save; a default flag set here is cleared from the user's other
        addresses in the same transaction, so a default moves, never clashes."""
        with transaction.atomic():
            others = Address.objects.filter(user=self.user).exclude(pk=self.pk)
            if self.is_default_shipping:
                others.filter(is_default_shipping=True).update(
                    is_default_shipping=False
                )
            if self.is_default_billing:
                others.filter(is_default_billing=True).update(is_default_billing=False)
            super().save(*args, **kwargs)

    @property
    def summary(self):
        """One line for dropdowns, e.g. ``Ada Lovelace — 12 Main St, Austin, TX 78701``."""
        street = f"{self.street}, {self.line2}" if self.line2 else self.street
        return f"{self.name} — {street}, {self.city}, {self.state} {self.zip}"

    def claim_empty_defaults(self, *, shipping=False, billing=False):
        """Become the default of each requested kind the user hasn't set."""
        others = Address.objects.filter(user=self.user).exclude(pk=self.pk)
        if shipping and not others.filter(is_default_shipping=True).exists():
            self.is_default_shipping = True
        if billing and not others.filter(is_default_billing=True).exists():
            self.is_default_billing = True
