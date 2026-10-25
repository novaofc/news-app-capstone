"""
Actions performed when an editor approves an article.

Kept separate from signals.py so each unit of work can be called and
tested on its own (and mocked in the tests).
"""

import logging

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


def get_subscriber_emails(article):
    """
    Return a sorted list of unique email addresses for readers who
    subscribe to the article's journalist or to its publisher.
    """
    user_model = get_user_model()
    subscribers = user_model.objects.filter(
        role="reader", subscribed_journalists=article.author
    )
    if article.publisher_id:
        subscribers = subscribers | user_model.objects.filter(
            role="reader", subscribed_publishers=article.publisher
        )
    emails = (
        subscribers.exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    return sorted(set(emails))


def build_article_email(article, recipients):
    """Build (but do not send) the email for an approved article."""
    source = article.publisher.name if article.publisher else "Independent"
    subject = f"New article: {article.title}"
    body = (
        f"{article.title}\n"
        f"By {article.author.get_full_name() or article.author.username}"
        f" | {source}\n\n"
        f"{article.content}\n\n"
        "You are receiving this because you subscribe to this "
        "journalist or publisher on The Daily Ledger."
    )
    # Subscribers go in BCC so readers never see each other's emails.
    return EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[],
        bcc=recipients,
    )


def email_subscribers(article):
    """
    Email an approved article to its subscribers.

    Returns the number of recipients emailed (0 if there were none
    or sending failed). Errors are logged, never raised, so a mail
    problem cannot undo an editor's approval.
    """
    recipients = get_subscriber_emails(article)
    if not recipients:
        logger.info("No subscribers to email for article %s", article.pk)
        return 0
    try:
        build_article_email(article, recipients).send(fail_silently=False)
    except Exception as error:  # noqa: BLE001 - mail failure is non-fatal
        logger.warning("Could not email article %s: %s", article.pk, error)
        return 0
    logger.info(
        "Emailed article %s to %d subscriber(s)",
        article.pk,
        len(recipients),
    )
    return len(recipients)


def build_approved_payload(article):
    """JSON body sent to the /api/approved/ endpoint."""
    return {
        "article_id": article.pk,
        "title": article.title,
        "content": article.content,
        "author": article.author.username,
        "publisher": article.publisher.name if article.publisher else None,
        "approved_by": (
            article.approved_by.username if article.approved_by else None
        ),
        "approved_at": (
            article.approved_at.isoformat() if article.approved_at else None
        ),
    }


def post_to_approved_endpoint(article):
    """
    POST the approved article to our own /api/approved/ endpoint
    using the requests module.

    Returns the Response, or None if the request failed. Failures are
    logged rather than raised.
    """
    try:
        response = requests.post(
            settings.APPROVED_ARTICLE_ENDPOINT,
            json=build_approved_payload(article),
            headers={"X-Api-Key": settings.APPROVED_API_KEY},
            timeout=settings.APPROVED_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning(
            "Could not POST article %s to %s: %s",
            article.pk,
            settings.APPROVED_ARTICLE_ENDPOINT,
            error,
        )
        return None
    logger.info("Logged article %s to /api/approved/", article.pk)
    return response
