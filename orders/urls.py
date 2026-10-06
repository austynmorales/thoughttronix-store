from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/add/<int:pk>/", views.AddToCartView.as_view(), name="add"),
    path(
        "cart/items/<int:pk>/increment/",
        views.IncrementCartItemView.as_view(),
        name="increment",
    ),
    path(
        "cart/items/<int:pk>/decrement/",
        views.DecrementCartItemView.as_view(),
        name="decrement",
    ),
    path(
        "cart/items/<int:pk>/remove/",
        views.RemoveCartItemView.as_view(),
        name="remove",
    ),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path(
        "checkout/discount/",
        views.DiscountPreviewView.as_view(),
        name="discount_preview",
    ),
    path(
        "checkout/address-fields/",
        views.AddressFieldsView.as_view(),
        name="address_fields",
    ),
    path("addresses/", views.AddressListView.as_view(), name="addresses"),
    path("addresses/new/", views.AddressCreateView.as_view(), name="address_create"),
    path(
        "addresses/<int:pk>/edit/",
        views.AddressUpdateView.as_view(),
        name="address_update",
    ),
    path(
        "addresses/<int:pk>/delete/",
        views.AddressDeleteView.as_view(),
        name="address_delete",
    ),
    path("orders/", views.OrderHistoryView.as_view(), name="history"),
    path("orders/<int:pk>/", views.OrderDetailView.as_view(), name="detail"),
    path(
        "orders/<int:pk>/confirmation/",
        views.OrderConfirmationView.as_view(),
        name="confirmation",
    ),
    # Back office — staff-only, pk URLs per the URL conventions.
    path(
        "backoffice/orders/",
        views.ManageOrderListView.as_view(),
        name="manage_orders",
    ),
    path(
        "backoffice/orders/<int:pk>/",
        views.ManageOrderDetailView.as_view(),
        name="manage_order_detail",
    ),
    path(
        "backoffice/orders/<int:pk>/status/",
        views.UpdateOrderStatusView.as_view(),
        name="manage_order_status",
    ),
    path(
        "backoffice/discounts/",
        views.ManageDiscountListView.as_view(),
        name="manage_discounts",
    ),
    path(
        "backoffice/discounts/new/",
        views.ManageDiscountCreateView.as_view(),
        name="manage_discount_create",
    ),
    path(
        "backoffice/discounts/<int:pk>/edit/",
        views.ManageDiscountUpdateView.as_view(),
        name="manage_discount_update",
    ),
]
