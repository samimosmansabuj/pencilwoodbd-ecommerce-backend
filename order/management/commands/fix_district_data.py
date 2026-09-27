from django.core.management.base import BaseCommand
from django.db.models import Q

from order.models import Order
from site_app.bd_districts import BD_DISTRICTS


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        district_lookup = {d.lower(): d for d in BD_DISTRICTS}

        orders = Order.objects.filter(
            Q(district__isnull=True) | Q(district=""),
            shipping_address__isnull=False,
        ).exclude(shipping_address="")

        fixed = 0
        skipped_no_comma = 0
        skipped_no_match = 0

        for order in orders:
            address = order.shipping_address.strip()

            if "," not in address:
                skipped_no_comma += 1
                continue

            address_part, _, tail = address.rpartition(",")
            tail = tail.strip()
            address_part = address_part.strip()

            matched_district = district_lookup.get(tail.lower())

            if not matched_district or not address_part:
                skipped_no_match += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Could not auto-fix Order #{order.order_id} "
                        f"(id={order.id}): shipping_address={order.shipping_address!r}"
                    )
                )
                continue

            self.stdout.write(
                f"Order #{order.order_id}: "
                f"shipping_address {order.shipping_address!r} -> {address_part!r}, "
                f"district -> {matched_district!r}"
            )

            if not dry_run:
                order.shipping_address = address_part
                order.district = matched_district
                order.save(update_fields=["shipping_address", "district"])

            fixed += 1

        self.stdout.write("")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY RUN] {fixed} order(s) would be fixed. "
                    f"{skipped_no_match} could not be auto-matched "
                    f"(no comma-separated district found or district not recognized). "
                    f"{skipped_no_comma} had no comma in shipping_address."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Fixed {fixed} order(s). "
                    f"{skipped_no_match} could not be auto-matched and need manual fixing. "
                    f"{skipped_no_comma} had no comma in shipping_address (left untouched)."
                )
            )
