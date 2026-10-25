"""
Data models for the News Application.

Tables (all in third normal form):

* CustomUser          - every account; ``role`` decides the user's group.
* Publisher           - a curated publication with editors and journalists.
* Article             - written by a journalist, optionally for a publisher.
* Newsletter          - a journalist's curated collection of articles.
* ApprovedArticleLog  - records received by the /api/approved/ endpoint.

Many-to-many relations (subscriptions, publisher staff, newsletter
articles) are stored in Django's automatic join tables, so no column
ever holds a list of values.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from . import roles


class CustomUser(AbstractUser):
    """
    A user of the news site with exactly one role.

    Reader-only fields:
        subscribed_publishers, subscribed_journalists

    Journalist-only data (reverse relations):
        articles, newsletters

    Fields that don't apply to a user's role are emptied when the
    user is saved, and the helper properties below return ``None``
    for them, as required by the brief.
    """

    role = models.CharField(
        max_length=20,
        choices=roles.ROLE_CHOICES,
        default=roles.READER,
    )
    email = models.EmailField("email address", blank=True)

    # --- Reader fields ---
    subscribed_publishers = models.ManyToManyField(
        "Publisher",
        blank=True,
        related_name="subscribers",
        help_text="Publishers this reader is subscribed to.",
    )
    subscribed_journalists = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="subscribers",
        limit_choices_to={"role": roles.JOURNALIST},
        help_text="Journalists this reader is subscribed to.",
    )

    class Meta:
        ordering = ["username"]

    def __str__(self):
        return self.username

    # --- Role helpers ---
    @property
    def is_reader(self):
        return self.role == roles.READER

    @property
    def is_editor(self):
        return self.role == roles.EDITOR

    @property
    def is_journalist(self):
        return self.role == roles.JOURNALIST

    # --- Role-specific field accessors ---
    @property
    def publisher_subscriptions(self):
        """Reader's publisher subscriptions, or None for other roles."""
        if not self.is_reader:
            return None
        return self.subscribed_publishers.all()

    @property
    def journalist_subscriptions(self):
        """Reader's journalist subscriptions, or None for other roles."""
        if not self.is_reader:
            return None
        return self.subscribed_journalists.all()

    @property
    def independent_articles(self):
        """Articles published without a publisher, or None for
        non-journalists."""
        if not self.is_journalist:
            return None
        return self.articles.filter(publisher__isnull=True)

    @property
    def independent_newsletters(self):
        """Newsletters authored by this journalist, or None for
        non-journalists."""
        if not self.is_journalist:
            return None
        return self.newsletters.all()

    def save(self, *args, **kwargs):
        """Save the user, then sync their role group and clear any
        fields that don't belong to their role."""
        super().save(*args, **kwargs)
        roles.assign_role_group(self)
        if not self.is_reader:
            # Journalists and editors cannot hold subscriptions.
            self.subscribed_publishers.clear()
            self.subscribed_journalists.clear()


class Publisher(models.Model):
    """A publication that employs editors and journalists."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="publishers_edited",
        limit_choices_to={"role": roles.EDITOR},
    )
    journalists = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="publishers_joined",
        limit_choices_to={"role": roles.JOURNALIST},
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("news:publisher_detail", args=[self.pk])


class Article(models.Model):
    """
    A news article written by a journalist.

    ``publisher`` is empty for independent articles. When it is set,
    the author must be one of that publisher's journalists.
    """

    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="articles",
        limit_choices_to={"role": roles.JOURNALIST},
    )
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        help_text="Leave empty for an independent article.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_articles",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("approve_article", "Can approve articles for publishing"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("news:article_detail", args=[self.pk])

    @property
    def is_independent(self):
        return self.publisher_id is None

    def clean(self):
        """Validate the author/publisher relationship."""
        super().clean()
        if self.author_id and not self.author.is_journalist:
            raise ValidationError(
                {"author": "Only journalists can author articles."}
            )
        if (
            self.publisher_id
            and self.author_id
            and not self.publisher.journalists.filter(
                pk=self.author_id
            ).exists()
        ):
            raise ValidationError(
                {
                    "publisher": (
                        "The author is not a journalist at this "
                        "publisher."
                    )
                }
            )

    def approve(self, editor):
        """
        Mark the article as approved by ``editor`` and save it.

        Saving triggers the post_save signal, which emails subscribers
        and logs the article to /api/approved/.
        """
        if self.approved:
            raise ValidationError("This article is already approved.")
        self.approved = True
        self.approved_by = editor
        self.approved_at = timezone.now()
        self.save()


class Newsletter(models.Model):
    """A curated collection of articles created by a journalist."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="newsletters",
        limit_choices_to={"role": roles.JOURNALIST},
    )
    articles = models.ManyToManyField(
        Article, blank=True, related_name="newsletters"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("news:newsletter_detail", args=[self.pk])

    def clean(self):
        super().clean()
        if self.author_id and not self.author.is_journalist:
            raise ValidationError(
                {"author": "Only journalists can author newsletters."}
            )


class ApprovedArticleLog(models.Model):
    """
    A record received by POST /api/approved/.

    ``payload`` stores the JSON exactly as it was received, so the log
    is an immutable snapshot even if the article is edited or deleted
    later.
    """

    article = models.ForeignKey(
        Article,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_logs",
    )
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        title = self.payload.get("title", "untitled")
        return f"Approved log: {title} ({self.received_at:%Y-%m-%d})"
