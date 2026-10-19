from __future__ import annotations

from typing import ClassVar

from django.db import models


class SchoolProfile(models.Model):
    """One row per school database: how the school presents itself on documents."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=200)
    motto = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    principal_name = models.CharField(max_length=120, blank=True)
    admission_prefix = models.CharField(
        max_length=10, default="NXE", help_text="Used in admission numbers, e.g. NXE/2026/0001"
    )
    report_card_footer = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def load(cls) -> SchoolProfile:
        profile, _ = cls.objects.get_or_create(pk=1, defaults={"name": "School"})
        return profile


class Counter(models.Model):
    """Gap-free document numbers (admission, invoice, receipt) per school and year."""

    name = models.CharField(max_length=30)
    year = models.PositiveSmallIntegerField()
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["name", "year"], name="uniq_counter_per_year")
        ]
