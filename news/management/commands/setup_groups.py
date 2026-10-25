"""python manage.py setup_groups - (re)build the role groups."""

from django.core.management.base import BaseCommand

from news.roles import ROLE_PERMISSIONS, ensure_role_groups


class Command(BaseCommand):
    help = "Create the Reader, Editor and Journalist groups and permissions."

    def handle(self, *args, **options):
        groups = ensure_role_groups()
        for role, group in groups.items():
            self.stdout.write(
                f"{group.name}: {', '.join(ROLE_PERMISSIONS[role])}"
            )
        self.stdout.write(self.style.SUCCESS("Role groups are up to date."))
