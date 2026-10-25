"""
Tests for the approval signal (Option 1 - Django signals).

Email uses Django's in-memory test backend (mail.outbox) and the
POST to /api/approved/ is mocked, so nothing leaves the test run.
"""

from unittest import mock

import requests
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from news import services
from news.models import ApprovedArticleLog, Article

from .base import NewsTestCase

API_KEY = "test-key"


@override_settings(
    APPROVED_API_KEY=API_KEY,
    APPROVED_ARTICLE_ENDPOINT="http://testserver/api/approved/",
)
class ApprovalSignalTests(NewsTestCase):
    def test_approval_emails_publisher_subscribers(self):
        self.pending_article.approve(self.editor)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "New article: Pending story")
        self.assertEqual(message.bcc, ["reader@example.com"])
        self.assertIn("Waiting for an editor.", message.body)

    def test_approval_emails_journalist_subscribers(self):
        article = Article.objects.create(
            title="Indie 2", content="Body", author=self.indie
        )
        article.approve(self.editor)
        self.assertEqual(mail.outbox[0].bcc, ["other_reader@example.com"])

    def test_each_subscriber_emailed_once(self):
        # Subscribed to both the journalist and the publisher.
        self.reader.subscribed_journalists.add(self.journalist)
        self.pending_article.approve(self.editor)
        self.assertEqual(mail.outbox[0].bcc, ["reader@example.com"])

    def test_no_email_when_there_are_no_subscribers(self):
        article = Article.objects.create(
            title="Lonely", content="Body", author=self.journalist
        )
        article.approve(self.editor)
        self.assertEqual(mail.outbox, [])

    def test_approval_posts_to_approved_endpoint(self):
        self.pending_article.approve(self.editor)
        self.mock_post.assert_called_once()
        args, kwargs = self.mock_post.call_args
        self.assertEqual(args[0], "http://testserver/api/approved/")
        self.assertEqual(kwargs["headers"], {"X-Api-Key": API_KEY})
        payload = kwargs["json"]
        self.assertEqual(payload["article_id"], self.pending_article.pk)
        self.assertEqual(payload["approved_by"], "editor")
        self.assertEqual(payload["publisher"], "Cape Chronicle")

    def test_saving_unapproved_article_does_nothing(self):
        self.pending_article.title = "Edited"
        self.pending_article.save()
        self.mock_post.assert_not_called()
        self.assertEqual(mail.outbox, [])

    def test_editing_approved_article_does_not_resend(self):
        self.publisher_article.title = "Typo fixed"
        self.publisher_article.save()
        self.mock_post.assert_not_called()
        self.assertEqual(mail.outbox, [])

    def test_endpoint_failure_does_not_break_approval(self):
        self.mock_post.side_effect = requests.ConnectionError("down")
        self.pending_article.approve(self.editor)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_failure_does_not_break_approval(self):
        with mock.patch(
            "news.services.EmailMessage.send",
            side_effect=OSError("SMTP down"),
        ):
            self.pending_article.approve(self.editor)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)
        self.mock_post.assert_called_once()

    def test_subscriber_lookup_ignores_blank_emails(self):
        self.reader.email = ""
        self.reader.save()
        self.assertEqual(
            services.get_subscriber_emails(self.pending_article), []
        )


@override_settings(APPROVED_API_KEY=API_KEY)
class ApprovedEndpointTests(NewsTestCase):
    url = reverse("api_approved")

    def payload(self):
        return services.build_approved_payload(self.publisher_article)

    def test_post_with_valid_key_creates_log(self):
        response = self.client.post(
            self.url, self.payload(), format="json",
            HTTP_X_API_KEY=API_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        log = ApprovedArticleLog.objects.get()
        self.assertEqual(log.article, self.publisher_article)
        self.assertEqual(log.payload["title"], "Publisher story")

    def test_post_without_key_is_rejected(self):
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ApprovedArticleLog.objects.exists())

    def test_post_with_wrong_key_is_rejected(self):
        response = self.client.post(
            self.url, self.payload(), format="json",
            HTTP_X_API_KEY="wrong",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_post_with_invalid_body_is_rejected(self):
        response = self.client.post(
            self.url, {"title": "no id"}, format="json",
            HTTP_X_API_KEY=API_KEY,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editor_can_read_log(self):
        ApprovedArticleLog.objects.create(
            article=self.publisher_article, payload=self.payload()
        )
        self.auth(self.editor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_reader_cannot_read_log(self):
        self.auth(self.reader)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
