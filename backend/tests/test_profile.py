"""People correct their own name and phone; email stays as the school set it."""

from __future__ import annotations

import pytest

from control_plane.models import PlatformAuditEvent, Role

pytestmark = pytest.mark.django_db


def test_people_update_their_own_name_and_phone(tenant, make_member, api):
    user = make_member(tenant, Role.TEACHER)
    client = api(user, None)
    response = client.patch(
        "/api/v1/me/",
        {"first_name": "  Kofi ", "last_name": "Boateng", "phone": "024 412 3456"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.data["first_name"] == "Kofi"
    assert response.data["phone"] == "+233244123456"
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Kofi", "Boateng")
    event = PlatformAuditEvent.objects.get(action="account.profile_updated")
    assert event.data == {"fields": ["first_name", "last_name", "phone"]}

    assert client.patch("/api/v1/me/", {"phone": ""}, format="json").data["phone"] == ""


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"first_name": "   "},
        {"first_name": "Visit www.spam.test"},
        {"phone": "12345"},
    ],
    ids=["nothing", "blank name", "link in name", "bad phone"],
)
def test_bad_profile_changes_are_refused(tenant, make_member, api, body):
    client = api(make_member(tenant, Role.TEACHER), None)
    assert client.patch("/api/v1/me/", body, format="json").status_code == 400


def test_email_cannot_be_changed_here(tenant, make_member, api):
    user = make_member(tenant, Role.TEACHER)
    response = api(user, None).patch(
        "/api/v1/me/", {"email": "new@example.test", "last_name": "Ok"}, format="json"
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email != "new@example.test"
