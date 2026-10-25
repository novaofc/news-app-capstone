"""Website routes (namespace "news")."""

from django.urls import path

from . import views

app_name = "news"

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    # Articles
    path("articles/new/", views.article_create, name="article_create"),
    path("articles/mine/", views.my_articles, name="my_articles"),
    path("articles/<int:pk>/", views.article_detail, name="article_detail"),
    path(
        "articles/<int:pk>/edit/",
        views.article_update,
        name="article_update",
    ),
    path(
        "articles/<int:pk>/delete/",
        views.article_delete,
        name="article_delete",
    ),
    # Editor review
    path("review/", views.review_queue, name="review_queue"),
    path(
        "review/<int:pk>/approve/",
        views.approve_article,
        name="approve_article",
    ),
    # Newsletters
    path("newsletters/", views.newsletter_list, name="newsletter_list"),
    path(
        "newsletters/new/",
        views.newsletter_create,
        name="newsletter_create",
    ),
    path(
        "newsletters/<int:pk>/",
        views.newsletter_detail,
        name="newsletter_detail",
    ),
    path(
        "newsletters/<int:pk>/edit/",
        views.newsletter_update,
        name="newsletter_update",
    ),
    path(
        "newsletters/<int:pk>/delete/",
        views.newsletter_delete,
        name="newsletter_delete",
    ),
    # Publishers, journalists, subscriptions
    path("publishers/", views.publisher_list, name="publisher_list"),
    path(
        "publishers/new/",
        views.publisher_create,
        name="publisher_create",
    ),
    path(
        "publishers/<int:pk>/edit/",
        views.publisher_update,
        name="publisher_update",
    ),
    path(
        "publishers/<int:pk>/",
        views.publisher_detail,
        name="publisher_detail",
    ),
    path(
        "journalists/<int:pk>/",
        views.journalist_detail,
        name="journalist_detail",
    ),
    path("subscriptions/", views.subscriptions, name="subscriptions"),
    path(
        "subscriptions/<str:kind>/<int:pk>/toggle/",
        views.toggle_subscription,
        name="toggle_subscription",
    ),
]
