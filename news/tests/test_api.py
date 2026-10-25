"""REST API tests: authentication, role permissions and subscriptions."""

from django.urls import reverse
from rest_framework import status

from news.models import Article, Newsletter

from .base import NewsTestCase

LIST_URL = reverse("article-list")
SUBSCRIBED_URL = reverse("article-subscribed")
PENDING_URL = reverse("article-pending")
NEWSLETTER_URL = reverse("newsletter-list")


def detail_url(pk):
    return reverse("article-detail", args=[pk])


def approve_url(pk):
    return reverse("article-approve", args=[pk])


class TokenAuthTests(NewsTestCase):
    def test_obtain_token_with_valid_credentials(self):
        response = self.client.post(
            reverse("api_token"),
            {"username": "reader", "password": "TestPass123!"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)

    def test_obtain_token_with_wrong_password_fails(self):
        response = self.client.post(
            reverse("api_token"),
            {"username": "reader", "password": "wrong"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-token")
        response = self.client.get(LIST_URL)
        self.assertEqual(
            response.status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_me_endpoint_hides_reader_fields_for_journalist(self):
        self.auth(self.journalist)
        response = self.client.get(reverse("api_me"))
        self.assertEqual(response.data["role"], "journalist")
        self.assertIsNone(response.data["subscribed_publishers"])
        self.assertEqual(response.data["article_count"], 2)

    def test_me_endpoint_hides_journalist_fields_for_reader(self):
        self.auth(self.reader)
        response = self.client.get(reverse("api_me"))
        self.assertEqual(
            response.data["subscribed_publishers"], [self.publisher.pk]
        )
        self.assertIsNone(response.data["article_count"])


class ArticleListTests(NewsTestCase):
    def test_every_role_can_list_articles(self):
        for user in (self.reader, self.editor, self.journalist):
            with self.subTest(role=user.role):
                self.auth(user)
                response = self.client.get(LIST_URL)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_only_contains_approved_articles(self):
        self.auth(self.reader)
        titles = {a["title"] for a in self.client.get(LIST_URL).data}
        self.assertEqual(titles, {"Publisher story", "Independent story"})

    def test_reader_can_retrieve_approved_article(self):
        self.auth(self.reader)
        response = self.client.get(detail_url(self.indie_article.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["author"], "indie")

    def test_reader_cannot_retrieve_unapproved_article(self):
        self.auth(self.reader)
        response = self.client.get(detail_url(self.pending_article.pk))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_author_can_retrieve_own_unapproved_article(self):
        self.auth(self.journalist)
        response = self.client.get(detail_url(self.pending_article.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_missing_article_returns_404(self):
        self.auth(self.reader)
        response = self.client.get(detail_url(9999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class SubscribedArticleTests(NewsTestCase):
    def test_reader_gets_publisher_subscription_articles_only(self):
        self.auth(self.reader)
        response = self.client.get(SUBSCRIBED_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [a["title"] for a in response.data]
        self.assertEqual(titles, ["Publisher story"])

    def test_reader_gets_journalist_subscription_articles_only(self):
        self.auth(self.other_reader)
        titles = [a["title"] for a in self.client.get(SUBSCRIBED_URL).data]
        self.assertEqual(titles, ["Independent story"])

    def test_unapproved_articles_are_never_in_subscribed_feed(self):
        self.auth(self.reader)
        titles = [a["title"] for a in self.client.get(SUBSCRIBED_URL).data]
        self.assertNotIn("Pending story", titles)

    def test_reader_with_no_subscriptions_gets_empty_list(self):
        self.reader.subscribed_publishers.clear()
        self.auth(self.reader)
        self.assertEqual(self.client.get(SUBSCRIBED_URL).data, [])

    def test_article_in_both_subscriptions_appears_once(self):
        self.reader.subscribed_journalists.add(self.journalist)
        self.auth(self.reader)
        titles = [a["title"] for a in self.client.get(SUBSCRIBED_URL).data]
        self.assertEqual(titles.count("Publisher story"), 1)

    def test_non_reader_cannot_use_subscribed_endpoint(self):
        self.auth(self.journalist)
        response = self.client.get(SUBSCRIBED_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ArticleCreateTests(NewsTestCase):
    def test_journalist_can_create_independent_article(self):
        self.auth(self.indie)
        response = self.client.post(
            LIST_URL, {"title": "Fresh", "content": "News body"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        article = Article.objects.get(pk=response.data["id"])
        self.assertEqual(article.author, self.indie)
        self.assertFalse(article.approved)
        self.assertIsNone(article.publisher)

    def test_journalist_can_create_article_for_own_publisher(self):
        self.auth(self.journalist)
        response = self.client.post(
            LIST_URL,
            {"title": "T", "content": "C", "publisher": self.publisher.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["publisher_name"], "Cape Chronicle")

    def test_journalist_cannot_post_to_other_publisher(self):
        self.auth(self.journalist)
        response = self.client.post(
            LIST_URL,
            {
                "title": "T",
                "content": "C",
                "publisher": self.other_publisher.pk,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("publisher", response.data)

    def test_journalist_cannot_self_approve_on_create(self):
        self.auth(self.indie)
        response = self.client.post(
            LIST_URL, {"title": "T", "content": "C", "approved": True}
        )
        self.assertFalse(response.data["approved"])

    def test_reader_cannot_create_article(self):
        self.auth(self.reader)
        response = self.client.post(LIST_URL, {"title": "T", "content": "C"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_cannot_create_article(self):
        self.auth(self.editor)
        response = self.client.post(LIST_URL, {"title": "T", "content": "C"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_fields_are_rejected(self):
        self.auth(self.indie)
        response = self.client.post(LIST_URL, {"title": "   "})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("title", response.data)
        self.assertIn("content", response.data)


class ArticleUpdateDeleteTests(NewsTestCase):
    payload = {"title": "Updated", "content": "Updated body"}

    def test_editor_can_update_any_article(self):
        self.auth(self.editor)
        response = self.client.put(
            detail_url(self.indie_article.pk), self.payload
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.indie_article.refresh_from_db()
        self.assertEqual(self.indie_article.title, "Updated")

    def test_journalist_can_update_own_article(self):
        self.auth(self.indie)
        response = self.client.put(
            detail_url(self.indie_article.pk), self.payload
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_journalist_cannot_update_someone_elses_article(self):
        self.auth(self.indie)
        response = self.client.put(
            detail_url(self.publisher_article.pk), self.payload
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reader_cannot_update(self):
        self.auth(self.reader)
        response = self.client.put(
            detail_url(self.indie_article.pk), self.payload
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_delete_article(self):
        self.auth(self.editor)
        response = self.client.delete(detail_url(self.indie_article.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Article.objects.filter(pk=self.indie_article.pk).exists()
        )

    def test_journalist_can_delete_own_article(self):
        self.auth(self.indie)
        response = self.client.delete(detail_url(self.indie_article.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_journalist_cannot_delete_someone_elses_article(self):
        self.auth(self.indie)
        response = self.client.delete(detail_url(self.publisher_article.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reader_cannot_delete(self):
        self.auth(self.reader)
        response = self.client.delete(detail_url(self.indie_article.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            Article.objects.filter(pk=self.indie_article.pk).exists()
        )


class ArticleApprovalApiTests(NewsTestCase):
    def test_editor_can_see_pending_queue(self):
        self.auth(self.editor)
        response = self.client.get(PENDING_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [a["title"] for a in response.data], ["Pending story"]
        )

    def test_journalist_cannot_see_pending_queue(self):
        self.auth(self.journalist)
        response = self.client.get(PENDING_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_approve(self):
        self.auth(self.editor)
        response = self.client.post(approve_url(self.pending_article.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["approved"])
        self.assertEqual(response.data["approved_by"], "editor")
        self.mock_post.assert_called_once()

    def test_approving_twice_returns_400(self):
        self.auth(self.editor)
        response = self.client.post(approve_url(self.publisher_article.pk))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_journalist_cannot_approve(self):
        self.auth(self.journalist)
        response = self.client.post(approve_url(self.pending_article.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.pending_article.refresh_from_db()
        self.assertFalse(self.pending_article.approved)

    def test_reader_cannot_approve(self):
        self.auth(self.reader)
        response = self.client.post(approve_url(self.pending_article.pk))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.mock_post.assert_not_called()


class NewsletterApiTests(NewsTestCase):
    def newsletter_url(self, pk=None):
        if pk is None:
            return NEWSLETTER_URL
        return reverse("newsletter-detail", args=[pk])

    def test_reader_can_list_and_view_newsletters(self):
        self.auth(self.reader)
        response = self.client.get(NEWSLETTER_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["title"], "Weekly")
        detail = self.client.get(self.newsletter_url(self.newsletter.pk))
        self.assertEqual(
            detail.data["articles"], [self.publisher_article.pk]
        )

    def test_journalist_can_create_newsletter(self):
        self.auth(self.indie)
        response = self.client.post(
            NEWSLETTER_URL,
            {
                "title": "Indie digest",
                "description": "My picks",
                "articles": [self.indie_article.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        newsletter = Newsletter.objects.get(pk=response.data["id"])
        self.assertEqual(newsletter.author, self.indie)
        self.assertEqual(list(newsletter.articles.all()),
                         [self.indie_article])

    def test_newsletter_cannot_include_unapproved_article(self):
        self.auth(self.journalist)
        response = self.client.post(
            NEWSLETTER_URL,
            {"title": "Bad", "articles": [self.pending_article.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reader_cannot_create_newsletter(self):
        self.auth(self.reader)
        response = self.client.post(NEWSLETTER_URL, {"title": "Nope"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_can_update_newsletter(self):
        self.auth(self.editor)
        response = self.client.patch(
            self.newsletter_url(self.newsletter.pk), {"title": "Renamed"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.newsletter.refresh_from_db()
        self.assertEqual(self.newsletter.title, "Renamed")

    def test_editor_cannot_create_newsletter(self):
        self.auth(self.editor)
        response = self.client.post(NEWSLETTER_URL, {"title": "Ed"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_journalist_cannot_delete_newsletter(self):
        self.auth(self.indie)
        response = self.client.delete(
            self.newsletter_url(self.newsletter.pk)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_delete_newsletter(self):
        self.auth(self.journalist)
        response = self.client.delete(
            self.newsletter_url(self.newsletter.pk)
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class PublisherApiTests(NewsTestCase):
    def test_reader_can_list_publishers(self):
        self.auth(self.reader)
        response = self.client.get(reverse("publisher-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chronicle = response.data[0]
        self.assertEqual(chronicle["name"], "Cape Chronicle")
        self.assertEqual(chronicle["journalists"], ["journalist"])

    def test_publishers_are_read_only(self):
        self.auth(self.editor)
        response = self.client.post(
            reverse("publisher-list"), {"name": "New"}
        )
        self.assertEqual(
            response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
