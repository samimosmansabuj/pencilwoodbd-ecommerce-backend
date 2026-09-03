from django.db import migrations

BUILTIN_HOME_SECTIONS = [
    ("hero_slider", "Hero Slider (Top Banner)", 0),
    ("kidz_product", "Kidz Product Slider", 10),
    ("filter_products_grid", "Product Filter + Grid", 20),
    ("social_proof_banner", "Social Proof Banner (500+ Customers etc.)", 30),
    ("why_choose", "Why Choose Pencilwood", 40),
    ("showcase", "See It in Real Life (Showcase)", 50),
    ("ecosystem", "Part of the Pencilwood Ecosystem", 60),
]

def seed_sections(apps, schema_editor):
    HomeSection = apps.get_model('site_app', 'HomeSection')
    for key, label, order in BUILTIN_HOME_SECTIONS:
        HomeSection.objects.get_or_create(
            section_key=key,
            defaults={
                "admin_label": label,
                "section_type": "builtin",
                "sort_order": order,
                "is_active": True,
            }
        )

def unseed_sections(apps, schema_editor):
    HomeSection = apps.get_model('site_app', 'HomeSection')
    keys = [k for k, _, _ in BUILTIN_HOME_SECTIONS]
    HomeSection.objects.filter(section_key__in=keys, section_type="builtin").delete()

class Migration(migrations.Migration):

    dependencies = [
        ('site_app', '0025_homesection_alter_about_whychooseus_options_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_sections, unseed_sections),
    ]