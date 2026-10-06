from django.contrib import admin

from .models import Address, Cart, CartItem, Order, OrderItem


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Read-only: the address book belongs to its customer."""

    list_display = ("user", "summary", "is_default_shipping", "is_default_billing")
    list_filter = ("is_default_shipping", "is_default_billing")
    search_fields = ("user__username", "name", "street", "city")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "item_count", "total")
    search_fields = ("user__username",)
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "status", "total", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "shipping_name")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
