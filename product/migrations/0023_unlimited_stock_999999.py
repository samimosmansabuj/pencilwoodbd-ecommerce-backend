from django.db import migrations

UNLIMITED_STOCK = 999999


def set_unlimited(apps, schema_editor):
    Product = apps.get_model("product", "Product")
    ProductVariant = apps.get_model("product", "ProductVariant")
    Product.objects.filter(inventory_type="unlimited").update(inventory_quantity=UNLIMITED_STOCK)
    ProductVariant.objects.filter(inventory_type="unlimited").update(inventory_quantity=UNLIMITED_STOCK)


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0022_addtocart_customization_note_and_more"),
    ]

    operations = [
        migrations.RunPython(set_unlimited, migrations.RunPython.noop),
    ]
