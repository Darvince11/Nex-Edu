"""Video links teachers paste on lessons, homework and parent meetings.

Any service works (owner's decision, 26 Oct 2026): Google Meet, Zoom, Teams,
WhatsApp and others. Nex Edu only checks the link is a plain https address with
no password in it, and names the service so the page can say "Join on Zoom".
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import models

SERVICES = {
    "meet.google.com": "Google Meet",
    "zoom.us": "Zoom",
    "teams.microsoft.com": "Microsoft Teams",
    "teams.live.com": "Microsoft Teams",
    "chat.whatsapp.com": "WhatsApp",
    "call.whatsapp.com": "WhatsApp",
    "wa.me": "WhatsApp",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
}


def validate_video_link(value: str) -> None:
    if not value:
        return
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        raise ValidationError("Paste the full link, starting with https://.")
    if parts.username or parts.password:
        raise ValidationError("The link can't contain a username or password.")


def service_name(value: str) -> str:
    """'Zoom', 'Google Meet'... or 'the link' for anything else."""
    host = (urlsplit(value).hostname or "").lower() if value else ""
    for domain, name in SERVICES.items():
        if host == domain or host.endswith(f".{domain}"):
            return name
    return "the link" if value else ""


class VideoLinkField(models.URLField):
    """An optional https video link."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("max_length", 500)
        kwargs.setdefault("blank", True)
        kwargs.setdefault(
            "help_text", "Online lesson or meeting link (Meet, Zoom, Teams, WhatsApp...)"
        )
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.validators.append(validate_video_link)
