"""A school's own roles: extra permissions for staff, given by the proprietor."""

from __future__ import annotations

import pytest

from control_plane.models import Role
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/school/roles/"


def _make_role(owner, **body):
    made = owner.post(
        URL,
        {"name": "Exams officer", "permissions": ["assessments.manage", "reports.view"], **body},
        format="json",
    )
    assert made.status_code == 201, made.content
    return made.json()


def test_a_custom_role_adds_permissions_to_a_staff_member(campus, make_member, make_student, api):
    owner = api(make_member(campus.tenant, Role.OWNER), campus.tenant)
    librarian_user = make_member(campus.tenant, Role.LIBRARIAN)
    librarian = api(librarian_user, campus.tenant)
    assert librarian.get("/api/v1/reports/class-list/").status_code == 403

    role = _make_role(owner)
    given = owner.post(f"{URL}{role['id']}/holders/", {"user": str(librarian_user.pk)})
    assert given.status_code == 201
    assert [h["email"] for h in given.json()["holders"]] == [librarian_user.email]

    assert librarian.get("/api/v1/reports/class-list/").status_code == 200
    me = api(librarian_user, None).get("/api/v1/me/").json()["schools"][0]
    assert me["custom_roles"] == ["Exams officer"]
    assert "assessments.manage" in me["permissions"] and me["roles"] == ["librarian"]

    # Taking it away (or the person leaving) ends it at once.
    owner.delete(f"{URL}{role['id']}/holders/?user={librarian_user.pk}")
    assert librarian.get("/api/v1/reports/class-list/").status_code == 403
    with tenant_context(campus.tenant):
        actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"custom_role.created", "custom_role.granted", "custom_role.revoked"} <= actions


def test_seeing_every_pupil_can_be_given(campus, make_member, make_student, api, assign):
    make_student(campus.tenant, arm=campus.jhs1)
    make_student(campus.tenant, arm=campus.jhs2)
    owner = api(make_member(campus.tenant, Role.OWNER), campus.tenant)
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    assign(teacher_user, campus.jhs1, campus.subjects["MTH"])
    teacher = api(teacher_user, campus.tenant)
    assert len(teacher.get("/api/v1/students/").json()["results"]) == 1
    role = _make_role(owner, name="Head of year", permissions=["students.view_all"])
    owner.post(f"{URL}{role['id']}/holders/", {"user": str(teacher_user.pk)})
    assert len(teacher.get("/api/v1/students/").json()["results"]) == 2


def test_custom_roles_cannot_escalate(campus, make_member, api):
    owner_user = make_member(campus.tenant, Role.OWNER)
    owner = api(owner_user, campus.tenant)
    for forbidden in ("members.manage", "school.branding", "assessments.amend", "finance.pay"):
        refused = owner.post(URL, {"name": "x", "permissions": [forbidden]}, format="json")
        assert refused.status_code == 400, forbidden
    role = _make_role(owner)
    # Only staff can hold one, and not the proprietor giving it to themselves.
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    assert owner.post(f"{URL}{role['id']}/holders/", {"user": str(parent.pk)}).status_code == 400
    assert (
        owner.post(f"{URL}{role['id']}/holders/", {"user": str(owner_user.pk)}).status_code == 403
    )
    # The head teacher can't manage custom roles.
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    assert head.get(URL).status_code == 403
    assert head.post(URL, {"name": "y", "permissions": ["reports.view"]}).status_code == 403


def test_a_role_belongs_to_one_school(campus, other_tenant, make_member, api):
    owner = api(make_member(campus.tenant, Role.OWNER), campus.tenant)
    role = _make_role(owner)
    other_owner = api(make_member(other_tenant, Role.OWNER), other_tenant)
    assert other_owner.get(URL).json()["roles"] == []
    assert other_owner.delete(f"{URL}{role['id']}/").status_code == 404
    # A blocked member's custom role stops working.
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    owner.post(f"{URL}{role['id']}/holders/", {"user": str(teacher_user.pk)})
    from control_plane.models import Membership

    Membership.objects.filter(user=teacher_user).update(is_active=False)
    me = api(teacher_user, None).get("/api/v1/me/").json()
    assert me["schools"] == []


def test_renaming_and_deleting(campus, make_member, api):
    owner = api(make_member(campus.tenant, Role.OWNER), campus.tenant)
    role = _make_role(owner)
    changed = owner.patch(
        f"{URL}{role['id']}/", {"name": "Exams and records officer"}, format="json"
    )
    assert changed.status_code == 200 and changed.json()["permissions"] == [
        "assessments.manage",
        "reports.view",
    ]
    duplicate = owner.post(
        URL, {"name": "exams and records officer", "permissions": ["reports.view"]}, format="json"
    )
    assert duplicate.status_code == 400
    assert owner.delete(f"{URL}{role['id']}/").status_code == 204
    assert owner.get(URL).json()["roles"] == []
