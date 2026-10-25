"""
Role definitions and the group/permission set-up that goes with them.

Every user has exactly one role. Each role maps to a Django Group of
the same name, and each group is given the model permissions listed
in ``ROLE_PERMISSIONS``. Access control throughout the project checks
these permissions (``user.has_perm(...)``) rather than hard-coding
role names wherever possible.
"""

from django.contrib.auth.models import Group, Permission

READER = "reader"
EDITOR = "editor"
JOURNALIST = "journalist"

ROLE_CHOICES = [
    (READER, "Reader"),
    (EDITOR, "Editor"),
    (JOURNALIST, "Journalist"),
]

# Group name used for each role.
ROLE_GROUPS = {
    READER: "Reader",
    EDITOR: "Editor",
    JOURNALIST: "Journalist",
}

# Permission codenames (app label "news") granted to each group.
ROLE_PERMISSIONS = {
    READER: [
        "view_article",
        "view_newsletter",
        "view_publisher",
    ],
    EDITOR: [
        "view_article",
        "change_article",
        "delete_article",
        "approve_article",
        "view_newsletter",
        "change_newsletter",
        "delete_newsletter",
        "view_publisher",
        "add_publisher",
        "change_publisher",
    ],
    JOURNALIST: [
        "add_article",
        "view_article",
        "change_article",
        "delete_article",
        "add_newsletter",
        "view_newsletter",
        "change_newsletter",
        "delete_newsletter",
        "view_publisher",
    ],
}


def ensure_role_groups():
    """
    Create the Reader, Editor and Journalist groups (if missing) and
    give each one exactly the permissions listed in ROLE_PERMISSIONS.

    Safe to run repeatedly. Returns a dict of role -> Group.
    """
    groups = {}
    for role, group_name in ROLE_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        permissions = Permission.objects.filter(
            content_type__app_label="news",
            codename__in=ROLE_PERMISSIONS[role],
        )
        group.permissions.set(permissions)
        groups[role] = group
    return groups


def assign_role_group(user):
    """
    Put ``user`` into the group that matches their role and remove
    them from the other role groups. Non-role groups are left alone.
    """
    group_name = ROLE_GROUPS.get(user.role)
    if group_name is None:
        return

    role_group, created = Group.objects.get_or_create(name=group_name)
    if created:
        # Group was missing (e.g. migrations ran without post_migrate);
        # build all groups so the new one gets its permissions.
        role_group = ensure_role_groups()[user.role]

    other_role_groups = Group.objects.filter(
        name__in=ROLE_GROUPS.values()
    ).exclude(pk=role_group.pk)
    user.groups.remove(*other_role_groups)
    user.groups.add(role_group)
