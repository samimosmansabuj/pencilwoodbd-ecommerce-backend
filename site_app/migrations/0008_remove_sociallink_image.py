# Generated by Django 5.1.2 on 2025-03-10 13:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('site_app', '0007_alter_contactinformation_email_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='sociallink',
            name='image',
        ),
    ]
