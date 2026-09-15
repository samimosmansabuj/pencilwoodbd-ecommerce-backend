from django.core.management.base import BaseCommand
from django.db.models import Q
from product.models import Product, generate_unique_slug


class Command(BaseCommand):
    help = "Backfill missing/blank slugs for Product rows without touching anything else."

    def handle(self, *args, **options):
        products = Product.objects.filter(Q(slug__isnull=True) | Q(slug=""))

        total = products.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ No products with missing slug found."))
            return

        fixed = 0
        for product in products:
            new_slug = generate_unique_slug(Product, product.name, None)
            Product.objects.filter(pk=product.pk).update(slug=new_slug)
            self.stdout.write(f"  -> [{product.pk}] {product.name}  =>  {new_slug}")
            fixed += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Fixed {fixed}/{total} products."))