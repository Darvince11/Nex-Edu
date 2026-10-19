from __future__ import annotations

from allauth.account.models import EmailAddress
from allauth.account.signals import password_reset
from django.core import mail

from apps.academics.models import ClassLevel, Period, Subject
from apps.assessments.models import AssessmentComponent, GradeBand
from apps.finance.models import LedgerAccount
from control_plane.models import Membership, Role, User
from control_plane.tenancy import tenant_context
from integrations.phone import normalize_gh_phone

# --- Ghanaian basic-school defaults ------------------------------------------------


def test_new_school_is_seeded_for_ghanaian_basic_education(tenant):
    with tenant_context(tenant):
        levels = list(ClassLevel.objects.values_list("name", flat=True))
        assert levels == [
            "KG 1",
            "KG 2",
            *[f"Basic {n}" for n in range(1, 7)],
            "JHS 1",
            "JHS 2",
            "JHS 3",
        ]
        assert not ClassLevel.objects.filter(name__startswith="SHS").exists()
        codes = set(Subject.objects.values_list("code", flat=True))
        assert {"ENG", "MTH", "SCI", "SOC", "RME", "CT", "CAD", "GHL", "OWOP"} <= codes
        bece = {
            b.grade: (b.min_score, b.max_score) for b in GradeBand.objects.filter(section="jhs")
        }
        assert set(bece) == {str(n) for n in range(1, 10)}
        assert bece["1"][0] == 80
        assert sum(c.max_score for c in AssessmentComponent.objects.all()) == 100
        assert LedgerAccount.objects.filter(code="1200").exists()


def test_ghanaian_phone_numbers():
    assert normalize_gh_phone("024 412 3456") == "+233244123456"
    assert normalize_gh_phone("+233 55 123 4567") == "+233551234567"
    assert normalize_gh_phone("233201234567") == "+233201234567"
    assert normalize_gh_phone("0302 123 456") is None  # landline
    assert normalize_gh_phone("0803 123 4567") is None  # Nigerian
    assert normalize_gh_phone("") is None


# --- Terms and timetable --------------------------------------------------------------


def test_set_current_term(campus, make_member, api):
    client = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    response = client.post(
        "/api/v1/academics/terms/",
        {
            "session": campus.session.pk,
            "number": 2,
            "starts_on": str(campus.term.ends_on),
            "ends_on": str(campus.session.ends_on),
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    second = response.data["id"]
    assert client.post(f"/api/v1/academics/terms/{second}/set_current/").status_code == 204
    assert client.get("/api/v1/academics/terms/current/").data["id"] == second


def test_term_must_fit_in_session(campus, make_member, api):
    client = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    response = client.post(
        "/api/v1/academics/terms/",
        {
            "session": campus.session.pk,
            "number": 3,
            "starts_on": "2020-01-01",
            "ends_on": "2020-03-01",
        },
        format="json",
    )
    assert response.status_code == 400


def test_timetable_rejects_class_and_teacher_clashes(campus, make_member, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    teacher = make_member(campus.tenant, Role.TEACHER)
    base = {
        "term": campus.term.pk,
        "weekday": 1,
        "starts_at": "08:00",
        "ends_at": "08:40",
        "teacher_user_id": str(teacher.pk),
    }
    ok = admin.post(
        "/api/v1/academics/periods/",
        {**base, "arm": str(campus.jhs1.pk), "subject": campus.subjects["MTH"].pk},
        format="json",
    )
    assert ok.status_code == 201, ok.content

    same_class = admin.post(
        "/api/v1/academics/periods/",
        {
            **base,
            "teacher_user_id": None,
            "arm": str(campus.jhs1.pk),
            "subject": campus.subjects["ENG"].pk,
            "starts_at": "08:20",
            "ends_at": "09:00",
        },
        format="json",
    )
    assert same_class.status_code == 400
    same_teacher = admin.post(
        "/api/v1/academics/periods/",
        {**base, "arm": str(campus.jhs2.pk), "subject": campus.subjects["MTH"].pk},
        format="json",
    )
    assert same_teacher.status_code == 400
    back_to_back = admin.post(
        "/api/v1/academics/periods/",
        {
            **base,
            "arm": str(campus.jhs1.pk),
            "subject": campus.subjects["ENG"].pk,
            "starts_at": "08:40",
            "ends_at": "09:20",
        },
        format="json",
    )
    assert back_to_back.status_code == 201
    with tenant_context(campus.tenant):
        assert Period.objects.count() == 2


def test_teachers_can_read_but_not_change_structure(campus, make_member, api):
    teacher = api(make_member(campus.tenant, Role.TEACHER), campus.tenant)
    assert teacher.get("/api/v1/academics/subjects/").status_code == 200
    assert (
        teacher.post(
            "/api/v1/academics/subjects/", {"name": "X", "code": "X"}, format="json"
        ).status_code
        == 403
    )


# --- Members ---------------------------------------------------------------------------


def test_invite_creates_login_and_sends_email(tenant, make_member, api):
    principal = api(make_member(tenant, Role.PRINCIPAL), tenant)
    response = principal.post(
        "/api/v1/members/",
        {
            "email": "Kofi@Example.test",
            "role": "teacher",
            "first_name": "Kofi",
            "phone": "024 412 3456",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    user = User.objects.get(email="kofi@example.test")
    assert user.phone == "+233244123456"
    assert not user.has_usable_password()
    assert Membership.objects.filter(user=user, tenant=tenant, role="teacher").exists()
    assert len(mail.outbox) == 1
    assert "Greenfield" in mail.outbox[0].subject
    assert "/account/password/reset/" in mail.outbox[0].body


def test_cannot_grant_more_access_than_you_have(tenant, make_member, api):
    admin = api(make_member(tenant, Role.ADMIN), tenant)
    assert (
        admin.post(
            "/api/v1/members/", {"email": "o@example.test", "role": "owner"}, format="json"
        ).status_code
        == 403
    )
    principal = api(make_member(tenant, Role.PRINCIPAL), tenant)
    # A bursar can manage finance; a head teacher can't, so can't create one.
    assert (
        principal.post(
            "/api/v1/members/", {"email": "b@example.test", "role": "bursar"}, format="json"
        ).status_code
        == 403
    )
    owner = api(make_member(tenant, Role.OWNER), tenant)
    assert (
        owner.post(
            "/api/v1/members/", {"email": "b@example.test", "role": "bursar"}, format="json"
        ).status_code
        == 201
    )


def test_deactivated_member_loses_access(tenant, make_member, api):
    owner = make_member(tenant, Role.OWNER)
    teacher = make_member(tenant, Role.TEACHER)
    membership = Membership.objects.get(user=teacher, tenant=tenant)
    client = api(owner, tenant)
    assert client.post(f"/api/v1/members/{membership.pk}/deactivate/").status_code == 200
    assert api(teacher, tenant).get("/api/v1/students/").status_code == 403
    own = Membership.objects.get(user=owner, tenant=tenant)
    assert client.post(f"/api/v1/members/{own.pk}/deactivate/").status_code == 400


def test_password_reset_verifies_invited_email(tenant):
    user = User.objects.create_user("new@example.test", None)
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=False)
    password_reset.send(sender=User, request=None, user=user)
    assert EmailAddress.objects.get(user=user).verified


def test_members_of_other_schools_are_not_listed(tenant, other_tenant, make_member, api):
    make_member(other_tenant, Role.TEACHER, email="elsewhere@example.test")
    emails = [
        m["email"]
        for m in api(make_member(tenant, Role.OWNER), tenant).get("/api/v1/members/").data
    ]
    assert "elsewhere@example.test" not in emails
