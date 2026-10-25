"""Admin site configuration."""

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError

from .models import (
    ApprovedArticleLog,
    Article,
    CustomUser,
    Newsletter,
    Publisher,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Role and subscriptions",
            {
                "fields": (
                    "role",
                    "subscribed_publishers",
                    "subscribed_journalists",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Role", {"fields": ("role", "email")}),
    )
    filter_horizontal = (
        "groups",
        "user_permissions",
        "subscribed_publishers",
        "subscribed_journalists",
    )


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    filter_horizontal = ("editors", "journalists")


@admin.action(description="Approve selected articles")
def approve_articles(modeladmin, request, queryset):
    """Approve one by one so the post_save signal fires for each
    (queryset.update() would skip signals)."""
    approved_count = 0
    for article in queryset.filter(approved=False):
        try:
            article.approve(request.user)
            approved_count += 1
        except ValidationError as error:
            modeladmin.message_user(
                request, f"{article}: {error}", messages.ERROR
            )
    modeladmin.message_user(
        request, f"Approved {approved_count} article(s)."
    )


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "title", "author", "publisher", "approved", "created_at"
    )
    list_filter = ("approved", "publisher")
    search_fields = ("title", "content")
    readonly_fields = ("approved_by", "approved_at")
    actions = [approve_articles]


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at")
    filter_horizontal = ("articles",)


@admin.register(ApprovedArticleLog)
class ApprovedArticleLogAdmin(admin.ModelAdmin):
    list_display = ("__str__", "article", "received_at")
    readonly_fields = ("article", "payload", "received_at")
