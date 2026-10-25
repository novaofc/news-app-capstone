"""
Signal handlers (implementation strategy: Option 1 - Django signals).

* pre_save / post_save on Article: when an article changes from
  "not approved" to "approved", email subscribers and POST the article
  to /api/approved/.
* m2m_changed on reader subscriptions: stop non-readers from holding
  subscriptions and stop readers subscribing to non-journalists.
* post_migrate: create the role groups and their permissions.
"""

from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from . import roles, services
from .models import Article, CustomUser


@receiver(pre_save, sender=Article)
def remember_previous_approval(sender, instance, **kwargs):
    """Store whether the article was already approved before this save,
    so post_save can tell if *this* save is the approval."""
    if instance.pk is None:
        instance._was_approved = False
        return
    instance._was_approved = (
        Article.objects.filter(pk=instance.pk, approved=True).exists()
    )


@receiver(post_save, sender=Article)
def handle_article_approval(sender, instance, created, **kwargs):
    """Email subscribers and log to /api/approved/ exactly once,
    when an article becomes approved."""
    if kwargs.get("raw"):
        # Loading fixtures - don't send emails or HTTP requests.
        return
    just_approved = instance.approved and not getattr(
        instance, "_was_approved", False
    )
    if not just_approved:
        return
    services.email_subscribers(instance)
    services.post_to_approved_endpoint(instance)


@receiver(m2m_changed, sender=CustomUser.subscribed_publishers.through)
@receiver(m2m_changed, sender=CustomUser.subscribed_journalists.through)
def restrict_subscriptions(sender, instance, action, reverse, pk_set,
                           **kwargs):
    """
    Only readers may subscribe, and only to journalists.

    Clearing/trimming ``pk_set`` during "pre_add" stops Django from
    adding those rows.
    """
    if action != "pre_add" or not pk_set:
        return
    is_journalist_relation = (
        sender is CustomUser.subscribed_journalists.through
    )

    if reverse:
        # e.g. publisher.subscribers.add(user) or
        # journalist.subscribers.add(user): pk_set holds the readers.
        if is_journalist_relation and not instance.is_journalist:
            pk_set.clear()
            return
        allowed_ids = CustomUser.objects.filter(
            pk__in=pk_set, role=roles.READER
        ).values_list("pk", flat=True)
    else:
        # e.g. reader.subscribed_journalists.add(journalist)
        if not instance.is_reader:
            pk_set.clear()
            return
        if not is_journalist_relation:
            return
        allowed_ids = CustomUser.objects.filter(
            pk__in=pk_set, role=roles.JOURNALIST
        ).values_list("pk", flat=True)

    pk_set.intersection_update(set(allowed_ids))


def create_role_groups(sender, **kwargs):
    """post_migrate handler (connected in apps.py)."""
    roles.ensure_role_groups()
