"""Model, role and group tests."""

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from news import roles
from news.models import Article

from .base import NewsTestCase, make_user


class RoleGroupTests(NewsTestCase):
    def test_user_is_added_to_group_matching_role(self):
        self.assertEqual(
            list(self.reader.groups.values_list("name", flat=True)),
            ["Reader"],
        )
        self.assertTrue(self.editor.groups.filter(name="Editor").exists())
        self.assertTrue(
            self.journalist.groups.filter(name="Journalist").exists()
        )

    def test_changing_role_moves_user_to_new_group(self):
        self.reader.role = roles.JOURNALIST
        self.reader.save()
        names = set(self.reader.groups.values_list("name", flat=True))
        self.assertEqual(names, {"Journalist"})

    def test_group_permissions_match_brief(self):
        reader = Group.objects.get(name="Reader")
        editor = Group.objects.get(name="Editor")
        journalist = Group.objects.get(name="Journalist")

        def codes(group):
            return set(group.permissions.values_list("codename", flat=True))

        self.assertNotIn("add_article", codes(reader))
        self.assertNotIn("change_article", codes(reader))
        self.assertIn("view_newsletter", codes(reader))
        self.assertIn("delete_article", codes(editor))
        self.assertIn("approve_article", codes(editor))
        self.assertNotIn("add_article", codes(editor))
        self.assertIn("add_article", codes(journalist))
        self.assertIn("add_newsletter", codes(journalist))
        self.assertNotIn("approve_article", codes(journalist))

    def test_user_permissions_come_from_group(self):
        self.assertTrue(self.journalist.has_perm("news.add_article"))
        self.assertFalse(self.reader.has_perm("news.add_article"))
        self.assertTrue(self.editor.has_perm("news.approve_article"))


class RoleFieldTests(NewsTestCase):
    def test_reader_fields_are_none_for_journalist(self):
        self.assertIsNone(self.journalist.publisher_subscriptions)
        self.assertIsNone(self.journalist.journalist_subscriptions)

    def test_journalist_fields_are_none_for_reader(self):
        self.assertIsNone(self.reader.independent_articles)
        self.assertIsNone(self.reader.independent_newsletters)

    def test_independent_articles_excludes_publisher_articles(self):
        self.assertEqual(
            list(self.indie.independent_articles), [self.indie_article]
        )
        self.assertNotIn(
            self.publisher_article, self.journalist.independent_articles
        )

    def test_reader_becoming_journalist_loses_subscriptions(self):
        self.reader.role = roles.JOURNALIST
        self.reader.save()
        self.assertFalse(self.reader.subscribed_publishers.exists())

    def test_non_reader_cannot_subscribe(self):
        self.journalist.subscribed_publishers.add(self.publisher)
        self.assertFalse(self.journalist.subscribed_publishers.exists())

    def test_reader_cannot_subscribe_to_non_journalist(self):
        self.reader.subscribed_journalists.add(self.editor, self.indie)
        self.assertEqual(
            list(self.reader.subscribed_journalists.all()), [self.indie]
        )


class ArticleValidationTests(NewsTestCase):
    def test_reader_cannot_author_article(self):
        article = Article(title="x", content="y", author=self.reader)
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_author_must_belong_to_publisher(self):
        article = Article(
            title="x", content="y", author=self.indie,
            publisher=self.publisher,
        )
        with self.assertRaises(ValidationError):
            article.full_clean()

    def test_independent_article_is_valid(self):
        article = Article(title="x", content="y", author=self.indie)
        article.full_clean()  # does not raise
        self.assertTrue(article.is_independent)

    def test_cannot_approve_twice(self):
        with self.assertRaises(ValidationError):
            self.publisher_article.approve(self.editor)

    def test_new_users_default_to_reader(self):
        user = make_user("plain", roles.READER)
        self.assertTrue(user.is_reader)
