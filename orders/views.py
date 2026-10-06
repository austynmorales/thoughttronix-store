"""Cart and checkout views — thin per the architecture convention.

The three HTMX interactions of the core live here: add-to-cart, quantity
change, and line removal. Each renders a partial (never ``base.html``);
the responses carry the navbar badge as an out-of-band swap via the
``oob_badge`` context flag. Checkout is conventional full-page work:
validate the form, hand everything to ``place_order``; its HTMX
touches fill an address section from the customer's address book and
preview a discount code in the order summary.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from accounts.mixins import StaffRequiredMixin
from products.models import Product

from .forms import AddressForm, CheckoutForm, DiscountCodeForm, OrderStatusForm
from .models import (
    Address,
    Cart,
    CartItem,
    DiscountCode,
    InvalidDiscountCode,
    Order,
)
from .services import place_order


def order_summary(cart, code_text):
    """Context for the checkout order summary, with ``code_text`` applied.

    A blank code means no discount; one that can't be redeemed comes back
    as ``discount_error`` and leaves the totals undiscounted.
    """
    code, error = None, None
    if code_text and code_text.strip():
        try:
            code = DiscountCode.objects.redeem(
                code_text, [line.product for line in cart.lines()]
            )
        except InvalidDiscountCode as invalid:
            error = str(invalid)
    discount = cart.discount(code)
    return {
        "cart": cart,
        "code": code,
        "discount": discount,
        "total": cart.total() - discount,
        "discount_error": error,
        "code_text": DiscountCode.normalize(code_text),
    }


class CartView(LoginRequiredMixin, TemplateView):
    """The customer's cart page."""

    template_name = "orders/cart.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cart"] = Cart.for_user(self.request.user)
        return context


class AddToCartView(LoginRequiredMixin, View):
    """HTMX: add a product; the button swaps and the badge updates OOB.

    Looks the product up through ``available()``, so adding an
    unavailable product 404s — the same not-for-sale semantics as the
    public catalog.
    """

    def post(self, request, pk):
        product = get_object_or_404(Product.objects.available(), pk=pk)
        item = Cart.for_user(request.user).add(product)
        return render(
            request,
            "orders/partials/_add_button.html",
            {"product": product, "in_cart": item.quantity, "oob_badge": True},
        )


class CartItemActionView(LoginRequiredMixin, View):
    """Base for HTMX line mutations: act, then re-render the cart contents.

    Items are always fetched through the owner's cart — never by bare pk.
    """

    def post(self, request, pk):
        item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
        self.act(item)
        return render(
            request,
            "orders/partials/_cart_contents.html",
            {"cart": item.cart, "oob_badge": True},
        )

    def act(self, item):
        raise NotImplementedError


class IncrementCartItemView(CartItemActionView):
    def act(self, item):
        item.increment()


class DecrementCartItemView(CartItemActionView):
    def act(self, item):
        item.decrement()


class RemoveCartItemView(CartItemActionView):
    def act(self, item):
        item.delete()


class CheckoutView(LoginRequiredMixin, FormView):
    """The single checkout page: validate the form, hand off to the service.

    A cart that can't check out (empty, or holding a product that has
    since become unavailable) is sent back to the cart page to be fixed —
    ``place_order`` enforces the same rules transactionally as the
    backstop.
    """

    template_name = "orders/checkout.html"
    form_class = CheckoutForm

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        cart = Cart.for_user(request.user)
        if not cart.items.exists():
            messages.info(request, "Your cart is empty — add something first.")
            return redirect("orders:cart")
        unavailable = [
            line.product.name for line in cart.lines() if not line.product.is_available
        ]
        if unavailable:
            messages.warning(
                request,
                f"No longer available: {', '.join(unavailable)}. "
                "Remove them from the cart to check out.",
            )
            return redirect("orders:cart")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Start from the customer's default addresses, when they have them."""
        initial = super().get_initial()
        addresses = self.request.user.addresses
        for prefix, address in [
            ("shipping", addresses.default_shipping()),
            ("billing", addresses.default_billing()),
        ]:
            if address:
                initial.update(
                    {f"{prefix}_{f}": getattr(address, f) for f in Address.FIELDS}
                )
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["cart"] = Cart.for_user(self.request.user)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # A re-rendered form keeps showing the discount it was submitted
        # with — unless the form rejected the code, which then shows
        # undiscounted, with the form's reason.
        cart = Cart.for_user(self.request.user)
        code_text = self.request.POST.get("discount_code", "")
        code_errors = context["form"].errors.get("discount_code")
        if code_errors:
            context.update(order_summary(cart, ""))
            context["discount_error"] = code_errors[0]
            context["code_text"] = DiscountCode.normalize(code_text)
        else:
            context.update(order_summary(cart, code_text))
        context["addresses"] = self.request.user.addresses.all()
        return context

    def form_valid(self, form):
        cart = Cart.for_user(self.request.user)
        try:
            order = place_order(
                cart,
                self.request.user,
                form.cleaned_data,
                coupon_code=form.cleaned_data["discount_code"] or None,
                save_shipping_address=form.cleaned_data["save_shipping_address"],
                save_billing_address=form.cleaned_data["save_billing_address"],
            )
        except InvalidDiscountCode as error:
            # The code went bad between validation and placement.
            form.add_error("discount_code", str(error))
            return self.form_invalid(form)
        messages.success(self.request, f"Order {order.number} placed. Thank you!")
        return redirect(reverse("orders:confirmation", kwargs={"pk": order.pk}))


class DiscountPreviewView(LoginRequiredMixin, View):
    """HTMX: re-render the checkout order summary with a code applied.

    A preview only — nothing is stored. The checkout POST re-checks the
    code through the form and ``place_order``.
    """

    def post(self, request):
        context = order_summary(
            Cart.for_user(request.user), request.POST.get("discount_code", "")
        )
        return render(
            request, "orders/partials/_order_summary.html", {**context, "oob": True}
        )


class AddressFieldsView(LoginRequiredMixin, TemplateView):
    """HTMX: re-render one checkout address section filled from a saved address.

    ``?section=shipping|billing&address=<pk>``. The address is fetched
    through its owner — another customer's pk 404s.
    """

    template_name = "orders/partials/_address_fields.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section = self.request.GET.get("section")
        pk = self.request.GET.get("address", "")
        if section not in ("shipping", "billing") or not pk.isdigit():
            raise Http404
        address = get_object_or_404(Address, pk=pk, user=self.request.user)
        form = CheckoutForm(
            initial={f"{section}_{f}": getattr(address, f) for f in Address.FIELDS}
        )
        context["fields"] = getattr(form, f"{section}_fields")()
        return context


# --- The address book ---------------------------------------------------------
#
# Plain full-page CRUD over the customer's own addresses. Deleting or
# editing never touches orders — they hold their own copies.


class OwnAddressesMixin(LoginRequiredMixin):
    """Addresses are always fetched through the owner — never by bare pk."""

    model = Address
    success_url = reverse_lazy("orders:addresses")

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class AddressListView(OwnAddressesMixin, ListView):
    template_name = "orders/address_list.html"
    context_object_name = "addresses"

    def get_queryset(self):
        return super().get_queryset().order_by("name")


class AddressCreateView(OwnAddressesMixin, SuccessMessageMixin, CreateView):
    """New address; the default checkboxes start ticked for any empty slot."""

    form_class = AddressForm
    template_name = "orders/address_form.html"
    success_message = "Address saved."

    def get_initial(self):
        addresses = self.get_queryset()
        return {
            "is_default_shipping": addresses.default_shipping() is None,
            "is_default_billing": addresses.default_billing() is None,
        }

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class AddressUpdateView(OwnAddressesMixin, SuccessMessageMixin, UpdateView):
    form_class = AddressForm
    template_name = "orders/address_form.html"
    success_message = "Address saved."


class AddressDeleteView(OwnAddressesMixin, SuccessMessageMixin, DeleteView):
    context_object_name = "address"
    template_name = "orders/address_confirm_delete.html"
    success_message = "Address deleted."


class OwnOrdersMixin(LoginRequiredMixin):
    """Orders are always fetched through the owner — never by bare pk."""

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderConfirmationView(OwnOrdersMixin, DetailView):
    template_name = "orders/confirmation.html"
    context_object_name = "order"


class OrderHistoryView(OwnOrdersMixin, ListView):
    """The customer's orders, most recent first per the model ordering."""

    template_name = "orders/order_history.html"
    context_object_name = "orders"


class OrderDetailView(OwnOrdersMixin, DetailView):
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return super().get_queryset().prefetch_related("items")


# --- The back office --------------------------------------------------------
#
# Staff-only order oversight: every customer's orders, filterable by
# status, with the status dropdown on the detail page. The ``section``
# context entry drives the active tab in the staff shell.


class ManageOrderListView(StaffRequiredMixin, ListView):
    """All orders, most recent first, filterable via ``?status=``."""

    template_name = "orders/manage_orders.html"
    context_object_name = "orders"
    paginate_by = 20
    extra_context = {"section": "orders"}

    def get_queryset(self):
        orders = Order.objects.select_related("user")
        status = self.request.GET.get("status", "")
        if status in Order.Status.values:
            orders = orders.filter(status=status)
        return orders

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = Order.Status.choices
        context["active_status"] = self.request.GET.get("status", "")
        return context


class ManageOrderDetailView(StaffRequiredMixin, DetailView):
    """Any order's detail, with the status form alongside."""

    template_name = "orders/manage_order_detail.html"
    context_object_name = "order"
    queryset = Order.objects.select_related("user").prefetch_related("items")
    extra_context = {"section": "orders"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = OrderStatusForm(instance=self.object)
        return context


class UpdateOrderStatusView(StaffRequiredMixin, View):
    """POST-only: set an order's status from the back-office dropdown."""

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderStatusForm(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"{order.number} is now {order.get_status_display().lower()}.",
            )
        else:
            messages.error(request, "That isn't a status an order can have.")
        return redirect("orders:manage_order_detail", pk=order.pk)


# --- Discount codes ---------------------------------------------------------
#
# List, create, and edit. No delete view: retiring (unticking Active) is
# how a code ends, and it can be undone.


class ManageDiscountListView(StaffRequiredMixin, ListView):
    template_name = "orders/manage_discounts.html"
    context_object_name = "codes"
    queryset = DiscountCode.objects.prefetch_related("products")
    extra_context = {"section": "discounts"}


class ManageDiscountCreateView(StaffRequiredMixin, SuccessMessageMixin, CreateView):
    model = DiscountCode
    form_class = DiscountCodeForm
    template_name = "orders/manage_discount_form.html"
    success_url = reverse_lazy("orders:manage_discounts")
    success_message = "Discount code %(code)s created."
    extra_context = {"section": "discounts"}


class ManageDiscountUpdateView(StaffRequiredMixin, SuccessMessageMixin, UpdateView):
    model = DiscountCode
    form_class = DiscountCodeForm
    template_name = "orders/manage_discount_form.html"
    success_url = reverse_lazy("orders:manage_discounts")
    success_message = "Discount code %(code)s saved."
    extra_context = {"section": "discounts"}
