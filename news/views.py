"""
Website views.

Access control uses Django's permission system: each view requires
the model permission its action needs (granted through the user's
role group), and journalists can only change their own work.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import roles
from .forms import ArticleForm, NewsletterForm, PublisherForm, SignUpForm
from .models import Article, CustomUser, Newsletter, Publisher

ARTICLES_PER_PAGE = 10


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def can_manage(user, obj):
    """Editors (and superusers) manage anything; journalists only
    their own articles/newsletters."""
    return user.is_superuser or user.is_editor or obj.author_id == user.pk


def get_visible_article(user, pk):
    """Fetch an article, hiding unapproved ones from users who
    neither wrote nor review it."""
    article = get_object_or_404(
        Article.objects.select_related("author", "publisher"), pk=pk
    )
    if not article.approved and not (
        user.has_perm("news.approve_article")
        or article.author_id == user.pk
    ):
        raise PermissionDenied("This article has not been published yet.")
    return article


def paginate(request, queryset):
    """Return one page of ``queryset`` based on the ``?page=`` value.

    Args:
        request: The current HTTP request.
        queryset: The items to split into pages.

    Returns:
        Page: The requested page. Invalid or missing page numbers
        fall back to a valid page instead of raising an error.
    """
    paginator = Paginator(queryset, ARTICLES_PER_PAGE)
    return paginator.get_page(request.GET.get("page"))


# ---------------------------------------------------------------------
# Public pages and accounts
# ---------------------------------------------------------------------
def home(request):
    """Front page: latest approved articles."""
    articles = Article.objects.filter(approved=True).select_related(
        "author", "publisher"
    )
    query = request.GET.get("q", "").strip()
    if query:
        articles = articles.filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )
    context = {
        "page_obj": paginate(request, articles),
        "query": query,
        "publishers": Publisher.objects.annotate(
            published=Count("articles", filter=Q(articles__approved=True))
        ),
    }
    return render(request, "news/home.html", context)


def signup(request):
    """Register as a Reader, Journalist or Editor and log in."""
    if request.user.is_authenticated:
        return redirect("news:home")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(
            request, f"Welcome, {user.username}! You joined as a "
            f"{user.get_role_display()}."
        )
        return redirect("news:home")
    return render(request, "registration/signup.html", {"form": form})


# ---------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------
@login_required
@permission_required("news.view_article", raise_exception=True)
def article_detail(request, pk):
    """Show a single article.

    Unapproved articles are only visible to their author and to
    editors. The template is told whether the user may edit or
    approve the article so it can show the right buttons.
    """
    article = get_visible_article(request.user, pk)
    context = {
        "article": article,
        "can_manage": can_manage(request.user, article)
        and request.user.has_perm("news.change_article"),
        "can_approve": not article.approved
        and request.user.has_perm("news.approve_article"),
    }
    return render(request, "news/article_detail.html", context)


@login_required
@permission_required("news.add_article", raise_exception=True)
def article_create(request):
    """Let a journalist write a new article.

    The article is saved as unapproved and waits in the review
    queue until an editor approves it.
    """
    form = ArticleForm(request.POST or None, author=request.user)
    if request.method == "POST" and form.is_valid():
        article = form.save()
        messages.success(
            request, "Article submitted. An editor will review it soon."
        )
        return redirect(article)
    return render(
        request,
        "news/article_form.html",
        {"form": form, "heading": "Write an article"},
    )


@login_required
@permission_required("news.change_article", raise_exception=True)
def article_update(request, pk):
    """Edit an existing article.

    Raises:
        PermissionDenied: If a journalist tries to edit an article
            they did not write.
    """
    article = get_object_or_404(Article, pk=pk)
    if not can_manage(request.user, article):
        raise PermissionDenied("You can only edit your own articles.")
    form = ArticleForm(request.POST or None, instance=article)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Article updated.")
        return redirect(article)
    return render(
        request,
        "news/article_form.html",
        {"form": form, "heading": "Edit article", "article": article},
    )


@login_required
@permission_required("news.delete_article", raise_exception=True)
def article_delete(request, pk):
    """Confirm on GET, then delete the article on POST.

    Editors are sent back to the review queue afterwards and
    journalists to their own dashboard.

    Raises:
        PermissionDenied: If a journalist tries to delete an article
            they did not write.
    """
    article = get_object_or_404(Article, pk=pk)
    if not can_manage(request.user, article):
        raise PermissionDenied("You can only delete your own articles.")
    if request.method == "POST":
        article.delete()
        messages.success(request, f"Deleted “{article.title}”.")
        if request.user.is_editor:
            return redirect("news:review_queue")
        return redirect("news:my_articles")
    return render(
        request,
        "news/confirm_delete.html",
        {"object": article, "kind": "article", "cancel_url": article},
    )


@login_required
@permission_required("news.add_article", raise_exception=True)
def my_articles(request):
    """Journalist dashboard: their articles and newsletters."""
    articles = request.user.articles.select_related("publisher")
    context = {
        "pending": articles.filter(approved=False),
        "published": articles.filter(approved=True),
        "newsletters": request.user.newsletters.all(),
        "publishers": request.user.publishers_joined.all(),
    }
    return render(request, "news/my_articles.html", context)


# ---------------------------------------------------------------------
# Editor review
# ---------------------------------------------------------------------
@login_required
@permission_required("news.approve_article", raise_exception=True)
def review_queue(request):
    """Articles waiting for an editor's approval."""
    pending = Article.objects.filter(approved=False).select_related(
        "author", "publisher"
    )
    recent = Article.objects.filter(approved=True).select_related(
        "author", "approved_by"
    ).order_by("-approved_at")[:5]
    return render(
        request,
        "news/review_queue.html",
        {"pending": pending, "recent": recent},
    )


@login_required
@permission_required("news.approve_article", raise_exception=True)
@require_POST
def approve_article(request, pk):
    """Approve an article. Saving it fires the post_save signal that
    emails subscribers and POSTs to /api/approved/."""
    article = get_object_or_404(Article, pk=pk)
    try:
        article.approve(request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(
            request,
            f"Approved “{article.title}”. Subscribers have been notified.",
        )
    return redirect("news:review_queue")


# ---------------------------------------------------------------------
# Newsletters
# ---------------------------------------------------------------------
@login_required
@permission_required("news.view_newsletter", raise_exception=True)
def newsletter_list(request):
    """List all newsletters with their author and article count."""
    newsletters = Newsletter.objects.select_related("author").annotate(
        article_total=Count("articles")
    )
    return render(
        request, "news/newsletter_list.html", {"newsletters": newsletters}
    )


@login_required
@permission_required("news.view_newsletter", raise_exception=True)
def newsletter_detail(request, pk):
    """Show one newsletter and the approved articles it contains."""
    newsletter = get_object_or_404(
        Newsletter.objects.select_related("author"), pk=pk
    )
    context = {
        "newsletter": newsletter,
        "articles": newsletter.articles.filter(approved=True)
        .select_related("author", "publisher"),
        "can_manage": can_manage(request.user, newsletter)
        and request.user.has_perm("news.change_newsletter"),
    }
    return render(request, "news/newsletter_detail.html", context)


@login_required
@permission_required("news.add_newsletter", raise_exception=True)
def newsletter_create(request):
    """Let a journalist create a new newsletter."""
    form = NewsletterForm(request.POST or None, author=request.user)
    if request.method == "POST" and form.is_valid():
        newsletter = form.save()
        messages.success(request, "Newsletter created.")
        return redirect(newsletter)
    return render(
        request,
        "news/newsletter_form.html",
        {"form": form, "heading": "Create a newsletter"},
    )


@login_required
@permission_required("news.change_newsletter", raise_exception=True)
def newsletter_update(request, pk):
    """Edit an existing newsletter.

    Raises:
        PermissionDenied: If a journalist tries to edit a newsletter
            they did not create.
    """
    newsletter = get_object_or_404(Newsletter, pk=pk)
    if not can_manage(request.user, newsletter):
        raise PermissionDenied("You can only edit your own newsletters.")
    form = NewsletterForm(request.POST or None, instance=newsletter)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Newsletter updated.")
        return redirect(newsletter)
    return render(
        request,
        "news/newsletter_form.html",
        {"form": form, "heading": "Edit newsletter"},
    )


@login_required
@permission_required("news.delete_newsletter", raise_exception=True)
def newsletter_delete(request, pk):
    """Confirm on GET, then delete the newsletter on POST.

    Raises:
        PermissionDenied: If a journalist tries to delete a newsletter
            they did not create.
    """
    newsletter = get_object_or_404(Newsletter, pk=pk)
    if not can_manage(request.user, newsletter):
        raise PermissionDenied("You can only delete your own newsletters.")
    if request.method == "POST":
        newsletter.delete()
        messages.success(request, "Newsletter deleted.")
        return redirect("news:newsletter_list")
    return render(
        request,
        "news/confirm_delete.html",
        {"object": newsletter, "kind": "newsletter",
         "cancel_url": newsletter},
    )


# ---------------------------------------------------------------------
# Publishers, journalists and subscriptions
# ---------------------------------------------------------------------
def publisher_list(request):
    """List all publishers with published-article and staff counts."""
    publishers = Publisher.objects.annotate(
        published=Count("articles", filter=Q(articles__approved=True)),
        staff=Count("journalists", distinct=True),
    )
    return render(
        request, "news/publisher_list.html", {"publishers": publishers}
    )


def publisher_detail(request, pk):
    """Show a publisher and a paginated list of its approved articles.

    Readers also see whether they are subscribed to this publisher.
    """
    publisher = get_object_or_404(Publisher, pk=pk)
    articles = publisher.articles.filter(approved=True).select_related(
        "author"
    )
    is_subscribed = (
        request.user.is_authenticated
        and request.user.is_reader
        and request.user.subscribed_publishers.filter(
            pk=publisher.pk
        ).exists()
    )
    context = {
        "publisher": publisher,
        "page_obj": paginate(request, articles),
        "is_subscribed": is_subscribed,
    }
    return render(request, "news/publisher_detail.html", context)


@login_required
@permission_required("news.add_publisher", raise_exception=True)
def publisher_create(request):
    """Editors create a publisher and choose its staff."""
    form = PublisherForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        publisher = form.save()
        messages.success(request, f"Created publisher “{publisher.name}”.")
        return redirect(publisher)
    return render(
        request,
        "news/publisher_form.html",
        {"form": form, "heading": "New publisher"},
    )


@login_required
@permission_required("news.change_publisher", raise_exception=True)
def publisher_update(request, pk):
    """Editors update a publisher's details and staff."""
    publisher = get_object_or_404(Publisher, pk=pk)
    form = PublisherForm(request.POST or None, instance=publisher)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Updated “{publisher.name}”.")
        return redirect(publisher)
    return render(
        request,
        "news/publisher_form.html",
        {"form": form, "heading": f"Edit {publisher.name}",
         "publisher": publisher},
    )


def journalist_detail(request, pk):
    """Show a journalist's profile, approved articles and newsletters.

    Only users with the Journalist role can be viewed here; any other
    user ID returns a 404. Readers also see whether they are
    subscribed to this journalist.
    """
    journalist = get_object_or_404(
        CustomUser, pk=pk, role=roles.JOURNALIST
    )
    articles = journalist.articles.filter(approved=True).select_related(
        "publisher"
    )
    is_subscribed = (
        request.user.is_authenticated
        and request.user.is_reader
        and request.user.subscribed_journalists.filter(
            pk=journalist.pk
        ).exists()
    )
    context = {
        "journalist": journalist,
        "page_obj": paginate(request, articles),
        "newsletters": journalist.newsletters.all(),
        "is_subscribed": is_subscribed,
    }
    return render(request, "news/journalist_detail.html", context)


def reader_required(view_func):
    """Decorator: only users with the Reader role."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        """Run the wrapped view only if the user is a reader.

        Raises:
            PermissionDenied: If the logged-in user is not a reader.
        """
        if not request.user.is_reader:
            raise PermissionDenied("Only readers can manage subscriptions.")
        return view_func(request, *args, **kwargs)

    return wrapper


@reader_required
def subscriptions(request):
    """A reader's subscriptions and a feed of their articles."""
    reader = request.user
    feed = Article.objects.filter(approved=True).filter(
        Q(author__in=reader.subscribed_journalists.all())
        | Q(publisher__in=reader.subscribed_publishers.all())
    ).select_related("author", "publisher").distinct()
    context = {
        "publishers": reader.subscribed_publishers.all(),
        "journalists": reader.subscribed_journalists.all(),
        "page_obj": paginate(request, feed),
        "other_publishers": Publisher.objects.exclude(
            pk__in=reader.subscribed_publishers.all()
        ),
        "other_journalists": CustomUser.objects.filter(
            role=roles.JOURNALIST
        ).exclude(pk__in=reader.subscribed_journalists.all()),
    }
    return render(request, "news/subscriptions.html", context)


@reader_required
@require_POST
def toggle_subscription(request, kind, pk):
    """Subscribe/unsubscribe to a publisher or journalist."""
    reader = request.user
    if kind == "publisher":
        target = get_object_or_404(Publisher, pk=pk)
        relation = reader.subscribed_publishers
    elif kind == "journalist":
        target = get_object_or_404(
            CustomUser, pk=pk, role=roles.JOURNALIST
        )
        relation = reader.subscribed_journalists
    else:
        raise PermissionDenied("Unknown subscription type.")

    if relation.filter(pk=target.pk).exists():
        relation.remove(target)
        messages.info(request, f"Unsubscribed from {target}.")
    else:
        relation.add(target)
        messages.success(request, f"Subscribed to {target}.")

    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return redirect(next_url)
    return redirect("news:subscriptions")
