from django.core.management.base import BaseCommand
from product.models import AddToCart, ProductVariant


class Command(BaseCommand):
    help = "Attach default variant to existing cart items"

    def handle(self, *args, **kwargs):
        cart_items = AddToCart.objects.filter(variant__isnull=True)

        updated = 0

        for item in cart_items:
            if item.product:
                default_variant = item.product.variants.first()
                if default_variant:
                    item.variant = default_variant  # NEW
                    item.save()
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"{updated} cart items updated with default variant."
        ))