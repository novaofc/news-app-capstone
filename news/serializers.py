"""DRF serializers for Article, User, Newsletter and Publisher."""

from rest_framework import serializers

from .models import (
    ApprovedArticleLog,
    Article,
    CustomUser,
    Newsletter,
    Publisher,
)


class UserSerializer(serializers.ModelSerializer):
    """
    Public view of a user.

    Subscription fields are shown for readers only and are ``None``
    for journalists/editors (and the article/newsletter counts are
    ``None`` for non-journalists), matching the role rules.
    """

    subscribed_publishers = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )
    subscribed_journalists = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True
    )
    article_count = serializers.SerializerMethodField()
    newsletter_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "role",
            "subscribed_publishers",
            "subscribed_journalists",
            "article_count",
            "newsletter_count",
        ]
        read_only_fields = fields

    def get_article_count(self, user):
        if not user.is_journalist:
            return None
        return user.articles.count()

    def get_newsletter_count(self, user):
        newsletters = user.independent_newsletters
        return None if newsletters is None else newsletters.count()

    def to_representation(self, user):
        data = super().to_representation(user)
        if not user.is_reader:
            data["subscribed_publishers"] = None
            data["subscribed_journalists"] = None
        return data


class PublisherSerializer(serializers.ModelSerializer):
    editors = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="username"
    )
    journalists = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="username"
    )

    class Meta:
        model = Publisher
        fields = [
            "id",
            "name",
            "description",
            "created_at",
            "editors",
            "journalists",
        ]
        read_only_fields = fields


class ArticleSerializer(serializers.ModelSerializer):
    """
    Article read/write serializer.

    ``author`` is always the logged-in journalist on create and never
    changes afterwards. Approval fields are read-only - articles are
    approved through the dedicated approve endpoint.
    """

    author = serializers.SlugRelatedField(
        read_only=True, slug_field="username"
    )
    publisher = serializers.PrimaryKeyRelatedField(
        queryset=Publisher.objects.all(),
        allow_null=True,
        required=False,
    )
    publisher_name = serializers.CharField(
        source="publisher.name", read_only=True, default=None
    )
    approved_by = serializers.SlugRelatedField(
        read_only=True, slug_field="username"
    )

    class Meta:
        model = Article
        fields = [
            "id",
            "title",
            "content",
            "author",
            "publisher",
            "publisher_name",
            "created_at",
            "updated_at",
            "approved",
            "approved_by",
            "approved_at",
        ]
        read_only_fields = [
            "created_at",
            "updated_at",
            "approved",
            "approved_by",
            "approved_at",
        ]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Content cannot be blank.")
        return value

    def validate(self, attrs):
        """The author must work for the chosen publisher."""
        if self.instance is not None:
            author = self.instance.author
        else:
            author = self.context["request"].user
        publisher = attrs.get(
            "publisher",
            self.instance.publisher if self.instance else None,
        )
        if publisher and not publisher.journalists.filter(
            pk=author.pk
        ).exists():
            raise serializers.ValidationError(
                {
                    "publisher": (
                        f"{author.username} is not a journalist at "
                        f"{publisher.name}."
                    )
                }
            )
        return attrs


class NewsletterSerializer(serializers.ModelSerializer):
    author = serializers.SlugRelatedField(
        read_only=True, slug_field="username"
    )
    articles = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Article.objects.filter(approved=True),
        required=False,
    )

    class Meta:
        model = Newsletter
        fields = [
            "id",
            "title",
            "description",
            "created_at",
            "author",
            "articles",
        ]
        read_only_fields = ["created_at"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title cannot be blank.")
        return value


class ApprovedArticleInputSerializer(serializers.Serializer):
    """Validates the JSON body POSTed to /api/approved/."""

    article_id = serializers.IntegerField()
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(allow_blank=True, required=False)
    author = serializers.CharField(max_length=150)
    publisher = serializers.CharField(
        max_length=150, allow_null=True, required=False
    )
    approved_by = serializers.CharField(
        max_length=150, allow_null=True, required=False
    )
    approved_at = serializers.DateTimeField(allow_null=True, required=False)

    def create(self, validated_data):
        article = Article.objects.filter(
            pk=validated_data["article_id"]
        ).first()
        # Store the original JSON (with dates as strings).
        return ApprovedArticleLog.objects.create(
            article=article, payload=dict(self.initial_data.items())
        )


class ApprovedArticleLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovedArticleLog
        fields = ["id", "article", "payload", "received_at"]
        read_only_fields = fields
