"""Guardian directory (one entry per person) and the school audit log filters."""

from __future__ import annotations

import pytest

from apps.students.models import StudentGuardian
from control_plane.models import Membership, Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db
URL = "/api/v1/guardians/"


@pytest.fixture
def family(campus, make_student):
    """Mrs Mensah has a child in JHS 1 and one in JHS 2; Mr Owusu has one in JHS 2."""
    a = make_student(campus.tenant, arm=campus.jhs1, first_name="Akua")
    b = make_student(campus.tenant, arm=campus.jhs2, first_name="Kojo")
    c = make_student(campus.tenant, arm=campus.jhs2, first_name="Yaw")
    with tenant_context(campus.tenant):
        for child in (a, b):
            StudentGuardian.objects.create(
                student=child,
                full_name="Ama Mensah",
                phone="024 412 3456",
                email="ama@example.test",
            )
        StudentGuardian.objects.create(student=c, full_name="Kofi Owusu", phone="0201112233")
    return {"a": a, "b": b, "c": c}


def test_each_guardian_is_listed_once_with_all_their_children(campus, family, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    people = {p["name"]: p for p in head.get(URL).data}
    assert set(people) == {"Ama Mensah", "Kofi Owusu"}
    children = " ".join(c["name"] for c in people["Ama Mensah"]["children"])
    assert "Akua" in children and "Kojo" in children
    assert len(people["Ama Mensah"]["children"]) == 2
    assert people["Ama Mensah"]["has_login"] is False
    assert [p["name"] for p in head.get(URL, {"q": "kojo"}).data] == ["Ama Mensah"]


def test_teachers_see_guardians_of_their_classes_and_parents_none(
    campus, family, make_member, assign, api
):
    teacher = make_member(campus.tenant, Role.TEACHER)
    assign(teacher, campus.jhs1, campus.subjects["ENG"])
    names = [p["name"] for p in api(teacher, campus.tenant).get(URL).data]
    assert names == ["Ama Mensah"]
    parent = api(make_member(campus.tenant, Role.PARENT, mfa=False), campus.tenant)
    assert parent.get(URL).status_code == 403


def test_inviting_a_guardian_links_the_login_to_every_child(campus, family, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    ama = next(p for p in head.get(URL).data if p["name"] == "Ama Mensah")
    invited = head.post(URL, {"key": ama["key"]}, format="json")
    assert invited.status_code == 201, invited.content
    assert invited.data == {"linked_children": 2}
    member = Membership.objects.get(user__email="ama@example.test", tenant=campus.tenant)
    assert member.role == Role.PARENT
    parent = api(member.user, campus.tenant)
    seen = {s["first_name"] for s in parent.get("/api/v1/students/").data["results"]}
    assert seen == {"Akua", "Kojo"}
    # Listed once still, now with a login; inviting again is refused.
    ama = next(p for p in head.get(URL).data if p["name"] == "Ama Mensah")
    assert ama["has_login"] is True
    assert head.post(URL, {"key": ama["key"]}, format="json").status_code == 400
    kofi = next(p for p in head.get(URL).data if p["name"] == "Kofi Owusu")
    no_email = head.post(URL, {"key": kofi["key"]}, format="json")
    assert no_email.status_code == 400
    assert "email" in str(no_email.data)


def test_school_audit_log_filters_by_kind_person_and_period(campus, family, make_member, api):
    head_user = make_member(campus.tenant, Role.PRINCIPAL, email="head@example.test")
    head = api(head_user, campus.tenant)
    head.post("/api/v1/staff/departments/", {"name": "Science"}, format="json")
    owner = api(make_member(campus.tenant, Role.OWNER), campus.tenant)
    events = owner.get("/api/v1/audit/events/", {"category": "staff."}).data["results"]
    assert events and all(e["action"].startswith("staff.") for e in events)
    by_head = owner.get("/api/v1/audit/events/", {"actor": "head@"}).data["results"]
    assert by_head and all(e["actor_email"] == "head@example.test" for e in by_head)
    assert owner.get("/api/v1/audit/events/", {"days": "1"}).status_code == 200
    teacher = api(make_member(campus.tenant, Role.TEACHER), campus.tenant)
    assert teacher.get("/api/v1/audit/events/").status_code == 403
