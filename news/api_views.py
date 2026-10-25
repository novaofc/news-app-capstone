"""
REST API views.

Endpoints (all under /api/):

    POST   token/                     obtain an auth token
    GET    articles/                  approved articles
    POST   articles/                  create (journalists)
    GET    articles/subscribed/       reader's subscribed content
    GET    articles/pending/          unapproved articles (editors)
    GET    articles/<id>/             one article
    PUT    articles/<id>/             update (editors / own journalist)
    PATCH  articles/<id>/             partial update
    DELETE articles/<id>/             delete (editors / own journalist)
    POST   articles/<id>/approve/     approve (editors)
    CRUD   newsletters/               newsletters
    GET    publishers/                publishers (read-only)
    GET    users/me/                  the logged-in user
    POST   approved/                  log an approved article (API key)
    GET    approved/                  approval log (editors)
"""

from django.core.exceptions import ValidationError
from django.db.models import Q
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ApprovedArticleLog, Article, Newsletter, Publisher
from .permissions import (
    ArticlePermission,
    CanApproveArticles,
    HasApprovedApiKey,
    IsReader,
    NewsletterPermission,
)
from .serializers import (
    ApprovedArticleInputSerializer,
    ApprovedArticleLogSerializer,
    ArticleSerializer,
    NewsletterSerializer,
    PublisherSerializer,
    UserSerializer,
)


def articles_visible_to(user):
    """
    Articles a user may see on detail/update/delete routes:
    every approved article, plus unapproved ones the user wrote
    (journalists) or must review (editors).
    """
    queryset = Article.objects.select_related(
        "author", "publisher", "approved_by"
    )
    if user.is_superuser or user.has_perm("news.approve_article"):
        return queryset
    return queryset.filter(Q(approved=True) | Q(author=user))


def subscribed_articles_for(reader):
    """Approved articles from the reader's subscribed journalists
    or publishers."""
    return (
        Article.objects.filter(approved=True)
        .filter(
            Q(author__in=reader.subscribed_journalists.all())
            | Q(publisher__in=reader.subscribed_publishers.all())
        )
        .select_related("author", "publisher", "approved_by")
        .distinct()
    )


class ArticleViewSet(viewsets.ModelViewSet):
    serializer_class = ArticleSerializer
    permission_classes = [ArticlePermission]

    def get_queryset(self):
        if self.action == "list":
            # GET /api/articles/ only ever lists approved articles.
            return Article.objects.filter(approved=True).select_related(
                "author", "publisher", "approved_by"
            )
        return articles_visible_to(self.request.user)

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[ArticlePermission, IsReader],
    )
    def subscribed(self, request):
        """GET /api/articles/subscribed/"""
        articles = subscribed_articles_for(request.user)
        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[CanApproveArticles],
    )
    def pending(self, request):
        """GET /api/articles/pending/ - review queue for editors."""
        articles = Article.objects.filter(approved=False).select_related(
            "author", "publisher"
        )
        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[CanApproveArticles],
    )
    def approve(self, request, pk=None):
        """POST /api/articles/<id>/approve/ - editors only."""
        article = self.get_object()
        try:
            article.approve(request.user)
        except ValidationError as error:
            return Response(
                {"detail": error.messages[0]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(article).data)


class NewsletterViewSet(viewsets.ModelViewSet):
    serializer_class = NewsletterSerializer
    permission_classes = [NewsletterPermission]
    queryset = Newsletter.objects.select_related("author").prefetch_related(
        "articles"
    )

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class PublisherViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PublisherSerializer
    queryset = Publisher.objects.prefetch_related("editors", "journalists")


class CurrentUserView(generics.RetrieveAPIView):
    """GET /api/users/me/"""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ApprovedArticleLogView(generics.ListCreateAPIView):
    """
    POST /api/approved/  - called by the approval signal (X-Api-Key).
    GET  /api/approved/  - editors can read the log.
    """

    queryset = ApprovedArticleLog.objects.all()

    def get_authenticators(self):
        # The internal POST authenticates with the API key, not a user,
        # so skip session auth (and its CSRF check) for it.
        if self.request.method == "POST":
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self.request.method == "POST":
            return [HasApprovedApiKey()]
        return [CanApproveArticles()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ApprovedArticleInputSerializer
        return ApprovedArticleLogSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        log = serializer.save()
        return Response(
            ApprovedArticleLogSerializer(log).data,
            status=status.HTTP_201_CREATED,
        )
