"""Forms used by the website (not the API)."""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from . import roles
from .models import Article, CustomUser, Newsletter, Publisher


class SignUpForm(UserCreationForm):
    """
    Public registration form.

    Visitors can register as a Reader, Journalist or Editor. Saving
    the user places them in the group that matches their role.
    """

    SIGNUP_ROLES = [
        (roles.READER, "Reader - follow journalists and publishers"),
        (roles.JOURNALIST, "Journalist - write and submit articles"),
        (roles.EDITOR, "Editor - review and approve articles"),
    ]

    email = forms.EmailField(
        required=True,
        help_text="Approved articles are emailed here.",
    )
    role = forms.ChoiceField(
        choices=SIGNUP_ROLES,
        widget=forms.RadioSelect,
        initial=roles.READER,
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "first_name", "last_name", "email", "role")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists."
            )
        return email


class ArticleForm(forms.ModelForm):
    """Create/edit an article. The publisher list only shows
    publishers the author actually writes for."""

    class Meta:
        model = Article
        fields = ["title", "content", "publisher"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 14}),
        }

    def __init__(self, *args, author=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            author = self.instance.author
        self.author = author
        self.fields["publisher"].required = False
        self.fields["publisher"].empty_label = "Independent (no publisher)"
        if author is not None:
            self.fields["publisher"].queryset = Publisher.objects.filter(
                journalists=author
            )

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Title cannot be blank.")
        return title

    def clean_content(self):
        content = self.cleaned_data["content"].strip()
        if not content:
            raise forms.ValidationError("Content cannot be blank.")
        return content

    def _post_clean(self):
        # Set the author before model.clean() runs its checks.
        if self.author is not None and not self.instance.author_id:
            self.instance.author = self.author
        super()._post_clean()


class NewsletterForm(forms.ModelForm):
    """Create/edit a newsletter from approved articles."""

    class Meta:
        model = Newsletter
        fields = ["title", "description", "articles"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "articles": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, author=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.author = author
        self.fields["articles"].queryset = Article.objects.filter(
            approved=True
        ).select_related("author", "publisher")
        self.fields["articles"].required = False

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Title cannot be blank.")
        return title

    def _post_clean(self):
        if self.author is not None and not self.instance.author_id:
            self.instance.author = self.author
        super()._post_clean()


class PublisherForm(forms.ModelForm):
    """Create/edit a publisher and choose its editors and journalists."""

    # Each list only offers users with the matching role.
    editors = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(role=roles.EDITOR),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    journalists = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.filter(role=roles.JOURNALIST),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Publisher
        fields = ["name", "description", "editors", "journalists"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name cannot be blank.")
        return name
