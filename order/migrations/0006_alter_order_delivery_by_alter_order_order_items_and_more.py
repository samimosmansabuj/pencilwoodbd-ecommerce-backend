# Generated by Django 5.1.6 on 2025-02-25 05:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0005_address_customer_alter_address_post_code_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='delivery_by',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='order_items',
            field=models.ManyToManyField(blank=True, null=True, to='order.orderitem'),
        ),
        migrations.AlterField(
            model_name='order',
            name='payment_type',
            field=models.CharField(choices=[('None', 'None'), ('COD', 'COD'), ('Online', 'Online'), ('Partial', 'Partial')], default='COD', max_length=50),
        ),
    ]
