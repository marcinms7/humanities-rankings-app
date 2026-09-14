from django.apps import AppConfig

class CoreConfig(AppConfig):
    name = 'backend.core'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import safeguards  # noqa: F401
