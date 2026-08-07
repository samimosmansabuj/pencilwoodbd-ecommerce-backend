from django.apps import AppConfig

class ForDashbaordConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashbaord'

    def ready(self):
        from django.db.models.signals import post_save
        from site_app.models import MaintenanceCost, maintenance_cost_saved
        post_save.connect(maintenance_cost_saved, sender=MaintenanceCost)