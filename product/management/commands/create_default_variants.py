from django.core.management.base import BaseCommand
from product.models import Product, ProductVariant


class Command(BaseCommand):
    help = "Create default variant for products without variants"

    def handle(self, *args, **kwargs):
        products = Product.objects.all()

        created_count = 0

        for product in products:
            if not product.variants.exists():  # NEW check
                ProductVariant.objects.create(
                    product=product,
                    sku=product.sku,  # NEW
                    price=product.price,  # NEW
                    discount_price=product.discount_price,  # NEW
                    cost_price=product.cost_price,  # NEW
                    inventory_quantity=product.inventory_quantity,  # NEW
                    weight=product.weight,  # NEW
                    dimensions=product.dimensions or {},  # NEW
                    attributes={},  # NEW default empty
                    is_active=True  # NEW
                )
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"{created_count} default variants created successfully."
        ))