"""The school's public website: a front page, a few pages and news.

Everything is plain text (tags are stripped when saved), so nothing a school
writes can run in a visitor's browser.
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from django.core.validators import RegexValidator
from django.db import models


class SiteSettings(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    published = models.BooleanField(default=False, help_text="Visitors can see the site")
    tagline = models.CharField(max_length=200, blank=True)
    about = models.TextField(max_length=4000, blank=True)
    address = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    office_hours = models.CharField(max_length=120, blank=True)
    show_events = models.BooleanField(default=True, help_text="List upcoming events for everyone")
    show_admissions = models.BooleanField(
        default=True, help_text="Link to the online admission form when Admissions is on"
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> SiteSettings:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Page(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(
        max_length=40,
        unique=True,
        validators=[
            RegexValidator(r"^[a-z0-9]+(-[a-z0-9]+)*$", "Lower-case letters, numbers and dashes.")
        ],
    )
    title = models.CharField(max_length=80)
    body = models.TextField(max_length=20000)
    order = models.PositiveSmallIntegerField(default=0)
    published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: ClassVar = ["order", "title"]


class NewsPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    body = models.TextField(max_length=8000)
    date = models.DateField()
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]
