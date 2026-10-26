"""School website: edited by leaders, public only once published, plain text only."""

from __future__ import annotations

import datetime as dt

import pytest
from django.test import Client
from django.utils import timezone

from apps.academics.models import CalendarEvent
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/website/"
PUBLIC = "/api/v1/public/site/"


@pytest.fixture
def site(campus, make_member, api):
    set_active(tenant=campus.tenant, code="website", active=True, request=None)
    return {
        "head": api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant),
        "teacher": api(make_member(campus.tenant, Role.TEACHER), campus.tenant),
    }


def visit(campus):
    return Client().get(PUBLIC, HTTP_X_TENANT=campus.tenant.slug)


def test_the_site_is_hidden_until_published_and_while_switched_off(campus, site):
    assert visit(campus).status_code == 404  # not published yet
    site["head"].patch(
        f"{URL}settings/", {"published": True, "tagline": "Knowledge is light"}, format="json"
    )
    shown = visit(campus)
    assert shown.status_code == 200 and shown.json()["tagline"] == "Knowledge is light"
    with tenant_context(campus.tenant):
        assert AuditEvent.objects.filter(action="website.published").exists()

    set_active(tenant=campus.tenant, code="website", active=False, request=None)
    assert visit(campus).status_code == 404
    assert site["head"].get(f"{URL}settings/").status_code == 403  # module off


def test_only_published_content_and_public_events_are_shown(campus, site):
    today = timezone.localdate()
    site["head"].patch(f"{URL}settings/", {"published": True}, format="json")
    site["head"].post(
        f"{URL}pages/",
        {"slug": "history", "title": "Our history", "body": "Founded 1998."},
        format="json",
    )
    site["head"].post(
        f"{URL}pages/",
        {"slug": "draft", "title": "Draft", "body": "Not yet", "published": False},
        format="json",
    )
    site["head"].post(
        f"{URL}news/",
        {"title": "Sports day", "body": "We won.", "date": today.isoformat()},
        format="json",
    )
    site["head"].post(
        f"{URL}news/",
        {"title": "Later", "body": "Scheduled", "date": (today + dt.timedelta(days=5)).isoformat()},
        format="json",
    )
    with tenant_context(campus.tenant):
        CalendarEvent.objects.create(title="Open day", starts_on=today, ends_on=today)
        CalendarEvent.objects.create(
            title="Staff training",
            starts_on=today,
            ends_on=today,
            audience=CalendarEvent.Audience.STAFF,
        )
    body = visit(campus).json()
    assert [p["slug"] for p in body["pages"]] == ["history"]
    assert [n["title"] for n in body["news"]] == ["Sports day"]
    assert [e["title"] for e in body["events"]] == ["Open day"]
    assert body["admissions_open"] is True  # admissions is on in the demo school
    # Nothing about people: no pupil or staff fields anywhere.
    assert set(body) == {
        "school",
        "tagline",
        "about",
        "contact",
        "admissions_open",
        "pages",
        "news",
        "events",
    }


def test_content_is_kept_as_plain_text(campus, site):
    page = (
        site["head"]
        .post(
            f"{URL}pages/",
            {
                "slug": "about-us",
                "title": "<b>About</b>",
                "body": "<script>alert(1)</script>Hello\x07 there",
            },
            format="json",
        )
        .json()
    )
    assert page["title"] == "About" and page["body"] == "alert(1)Hello there"
    bad_slug = site["head"].post(
        f"{URL}pages/", {"slug": "About Us!", "title": "x", "body": "x"}, format="json"
    )
    assert bad_slug.status_code == 400


def test_only_leaders_edit_the_site(campus, site):
    assert site["teacher"].get(f"{URL}settings/").status_code == 403
    assert (
        site["teacher"]
        .post(f"{URL}news/", {"title": "x", "body": "x", "date": "2026-01-01"})
        .status_code
        == 403
    )
