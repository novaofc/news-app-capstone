from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "news"
    verbose_name = "News"

    def ready(self):
        # Importing the module registers the @receiver handlers.
        from . import signals

        # Build the role groups after this app's permissions exist.
        post_migrate.connect(signals.create_role_groups, sender=self)
