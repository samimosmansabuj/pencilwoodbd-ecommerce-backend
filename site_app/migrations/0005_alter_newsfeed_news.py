# Generated by Django 5.1.6 on 2025-03-09 09:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('site_app', '0004_alter_homeslider_image_alter_homeslider_title'),
    ]

    operations = [
        migrations.AlterField(
            model_name='newsfeed',
            name='news',
            field=models.CharField(max_length=255),
        ),
    ]
