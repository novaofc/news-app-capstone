"""Application configuration for the news app.

Registers the app with Django and wires up its signal handlers
once the app registry is fully loaded.
"""

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NewsConfig(AppConfig):
    """Django configuration for the ``news`` application.

    Sets the default primary key type and the human-readable name
    shown in the admin, and connects signals when the app is ready.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "news"
    verbose_name = "News"

    def ready(self):
        """Connect the app's signal handlers when Django starts.

        Importing the ``signals`` module registers its ``@receiver``
        handlers. The ``create_role_groups`` handler is connected to
        ``post_migrate`` so the Reader, Editor and Journalist groups are
        built after this app's permissions exist in the database.
        """
        # Importing the module registers the @receiver handlers.
        from . import signals

        # Build the role groups after this app's permissions exist.
        post_migrate.connect(signals.create_role_groups, sender=self)
