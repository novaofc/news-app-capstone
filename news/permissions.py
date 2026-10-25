"""
REST API permission classes.

Each class checks the Django model permissions that the user's role
group grants (see roles.py), plus ownership rules for journalists.
"""

import hmac

from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission

# HTTP method -> model permission action
METHOD_ACTIONS = {
    "POST": "add",
    "PUT": "change",
    "PATCH": "change",
    "DELETE": "delete",
}


def has_model_perm(user, action, model_name):
    """True if ``user`` has e.g. news.change_article."""
    return user.has_perm(f"news.{action}_{model_name}")


class RoleModelPermission(BasePermission):
    """
    Base class for Article and Newsletter permissions.

    * Reading needs ``view_<model>`` (all roles have it).
    * Writing needs the matching add/change/delete permission, so:
      only journalists can create, editors and journalists can
      update/delete, readers can only view.
    * Journalists may only update/delete their own items; editors may
      update/delete any.
    """

    model_name = None

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return has_model_perm(user, "view", self.model_name)
        action = METHOD_ACTIONS.get(request.method)
        return bool(action) and has_model_perm(
            user, action, self.model_name
        )

    def has_object_permission(self, request, view, obj):
        user = request.user
        if request.method in SAFE_METHODS:
            return True
        if user.is_superuser or user.is_editor:
            return True
        return obj.author_id == user.pk


class ArticlePermission(RoleModelPermission):
    model_name = "article"


class NewsletterPermission(RoleModelPermission):
    model_name = "newsletter"


class CanApproveArticles(BasePermission):
    """Only users with news.approve_article (the Editor group)."""

    message = "Only editors can approve articles."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.has_perm("news.approve_article")
        )


class IsReader(BasePermission):
    """Only users with the Reader role."""

    message = "Only readers have subscriptions."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_reader)


class HasApprovedApiKey(BasePermission):
    """
    Allows the request if it carries the shared X-Api-Key header.

    Used by POST /api/approved/ so that only this application's own
    signal can write to the approval log.
    """

    message = "A valid X-Api-Key header is required."

    def has_permission(self, request, view):
        supplied = request.headers.get("X-Api-Key", "")
        return hmac.compare_digest(supplied, settings.APPROVED_API_KEY)
