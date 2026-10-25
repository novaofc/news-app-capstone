"""Shared test fixtures."""

from unittest import mock

from django.core import mail
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from news import roles
from news.models import Article, CustomUser, Newsletter, Publisher


def make_user(username, role, **extra):
    return CustomUser.objects.create_user(
        username=username,
        password="TestPass123!",
        email=extra.pop("email", f"{username}@example.com"),
        role=role,
        **extra,
    )


class NewsTestCase(APITestCase):
    """
    Builds a small newsroom for every test:

    * publisher "Cape Chronicle" with editor + journalist
    * an independent journalist
    * two readers: one subscribed to the publisher, one to the
      independent journalist
    * approved and unapproved articles

    ``requests.post`` (used by the approval signal) is mocked for every
    test so no real HTTP request is ever made.
    """

    def setUp(self):
        patcher = mock.patch("news.services.requests.post")
        self.mock_post = patcher.start()
        self.addCleanup(patcher.stop)

        self.editor = make_user("editor", roles.EDITOR)
        self.journalist = make_user("journalist", roles.JOURNALIST)
        self.indie = make_user("indie", roles.JOURNALIST)
        self.reader = make_user("reader", roles.READER)
        self.other_reader = make_user("other_reader", roles.READER)

        self.publisher = Publisher.objects.create(name="Cape Chronicle")
        self.other_publisher = Publisher.objects.create(name="Karoo Times")
        self.publisher.editors.add(self.editor)
        self.publisher.journalists.add(self.journalist)

        self.reader.subscribed_publishers.add(self.publisher)
        self.other_reader.subscribed_journalists.add(self.indie)

        self.publisher_article = Article.objects.create(
            title="Publisher story",
            content="From the Chronicle.",
            author=self.journalist,
            publisher=self.publisher,
            approved=True,
        )
        self.indie_article = Article.objects.create(
            title="Independent story",
            content="Written independently.",
            author=self.indie,
            approved=True,
        )
        self.pending_article = Article.objects.create(
            title="Pending story",
            content="Waiting for an editor.",
            author=self.journalist,
            publisher=self.publisher,
        )
        self.newsletter = Newsletter.objects.create(
            title="Weekly",
            description="Best of the week.",
            author=self.journalist,
        )
        self.newsletter.articles.add(self.publisher_article)

        # Approvals in setUp should not count towards test assertions.
        self.mock_post.reset_mock()
        mail.outbox = []

    def auth(self, user):
        """Authenticate the API client with the user's token."""
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def logout(self):
        self.client.credentials()
