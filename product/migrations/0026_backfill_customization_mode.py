from django.db import migrations


def backfill(apps, schema_editor):
    Product = apps.get_model("product", "Product")
    AddToCart = apps.get_model("product", "AddToCart")

    # Products that had customization switched on before the new mode field
    # existed keep working as "optional" (customer picks Standard / Customized).
    Product.objects.filter(has_customization=True, customization_mode="off").update(
        customization_mode="optional"
    )

    # Cart lines that already carry a customization note were customized lines.
    AddToCart.objects.exclude(customization_note="").filter(is_customized=False).update(
        is_customized=True
    )


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0025_addtocart_customization_price_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
