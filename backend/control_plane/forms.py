"""Extra sign-up fields. allauth adds email and password; the headless API accepts
these as JSON alongside them (``ACCOUNT_SIGNUP_FORM_CLASS``)."""

from __future__ import annotations

import re
from typing import Any

from django import forms
from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone

_LINKISH = re.compile(r"(://|www\.|\.(com|net|org|xyz|top|ru|info)\b)", re.IGNORECASE)


def clean_person_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise forms.ValidationError("Enter your name.")
    # Names appear in emails we send; refusing links stops sign-up being used for spam.
    if _LINKISH.search(value) or any(c in value for c in "<>@"):
        raise forms.ValidationError("Enter your name without links or symbols.")
    return value


class SignupForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    accept_terms = forms.BooleanField(
        required=True,
        error_messages={"required": "Agree to the terms and privacy notice to continue."},
    )
    # Honeypot: hidden from people, filled in by form-stuffing bots. allauth's own
    # honeypot (ACCOUNT_SIGNUP_FORM_HONEYPOT_FIELD) only works for its HTML forms,
    # not the headless API, hence this. No account is created and no email is sent.
    website = forms.CharField(required=False, max_length=200)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        if cleaned.get("website"):
            raise forms.ValidationError("We couldn't create your account. Please try again.")
        return cleaned

    def clean_first_name(self) -> str:
        return clean_person_name(self.cleaned_data["first_name"])

    def clean_last_name(self) -> str:
        return clean_person_name(self.cleaned_data["last_name"])

    def signup(self, request: HttpRequest, user: Any) -> None:
        """Called by allauth once the account exists. Records Act 843 consent."""
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.terms_accepted_at = timezone.now()
        user.terms_version = settings.TERMS_VERSION
        user.save(update_fields=["first_name", "last_name", "terms_accepted_at", "terms_version"])
