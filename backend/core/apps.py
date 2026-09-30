from django.apps import AppConfig

class CoreConfig(AppConfig):
    name = 'backend.core'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import safeguards  # noqa: F401
        from .catalog_cache import connect_catalog_invalidation
        connect_catalog_invalidation()

        from .search import connect_search_invalidation
        connect_search_invalidation()
