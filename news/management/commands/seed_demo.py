"""
python manage.py seed_demo

Creates demo users (one per role), a publisher and some articles so
the site and API can be explored straight away. Safe to run twice.
All demo accounts use the password given by --password.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from news import roles
from news.models import Article, CustomUser, Newsletter, Publisher

DEMO_USERS = [
    ("reader1", roles.READER, "Rea", "Der"),
    ("editor1", roles.EDITOR, "Edie", "Torres"),
    ("journalist1", roles.JOURNALIST, "Jo", "Naledi"),
    ("journalist2", roles.JOURNALIST, "Sam", "Indie"),
]


class Command(BaseCommand):
    help = "Create demo users, a publisher, articles and a newsletter."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="DemoPass123!",
            help="Password for every demo account.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        users = {}
        for username, role, first, last in DEMO_USERS:
            user, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "email": f"{username}@example.com",
                },
            )
            if created:
                user.set_password(options["password"])
                user.save()
            users[username] = user

        publisher, _ = Publisher.objects.get_or_create(
            name="Cape Chronicle",
            defaults={"description": "City news from the Mother City."},
        )
        publisher.editors.add(users["editor1"])
        publisher.journalists.add(users["journalist1"])

        approved, _ = Article.objects.get_or_create(
            title="Harbour upgrade opens to the public",
            defaults={
                "content": "The newly upgraded harbour walkway opened "
                "this morning to large crowds.",
                "author": users["journalist1"],
                "publisher": publisher,
            },
        )
        if not approved.approved:
            approved.approve(users["editor1"])

        Article.objects.get_or_create(
            title="Independent: the quiet rise of community gardens",
            defaults={
                "content": "Across the city, residents are turning "
                "empty lots into vegetable gardens.",
                "author": users["journalist2"],
            },
        )

        newsletter, _ = Newsletter.objects.get_or_create(
            title="Weekend Briefing",
            defaults={
                "description": "The week's stories worth your time.",
                "author": users["journalist1"],
            },
        )
        newsletter.articles.add(approved)

        reader = users["reader1"]
        reader.subscribed_publishers.add(publisher)
        reader.subscribed_journalists.add(users["journalist2"])

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready. Log in as reader1, editor1, journalist1 or "
            f"journalist2 with password {options['password']}"
        ))
