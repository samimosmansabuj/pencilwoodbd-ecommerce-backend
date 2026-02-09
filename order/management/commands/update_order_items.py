from django.core.management.base import BaseCommand
from django.db.models import F
from order.models import OrderItem


class Command(BaseCommand):
    help = "Update OrderItem objects without calling save()"

    def handle(self, *args, **options):
        qs = OrderItem.objects.all()

        updated_count = qs.update(
            discount_total_price=F("discount_price") * F("quantity")
        )

        self.stdout.write(
            self.style.SUCCESS(f"✅ Updated {updated_count} OrderItem rows")
        )
