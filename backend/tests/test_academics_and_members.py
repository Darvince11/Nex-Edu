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
    owner = api(make_member(tenant, Role.OWNER), tenant)
    response = owner.post(
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

    owner = api(make_member(tenant, Role.OWNER), tenant)
    assert (
        owner.post(
            "/api/v1/members/", {"email": "b@example.test", "role": "bursar"}, format="json"
        ).status_code
        == 201
    )


def test_administrator_sees_staff_but_gives_no_staff_access(tenant, make_member, api):
    """The administrator sees who has access and invites parents, but can't give,
    resend or remove staff access."""
    client = api(make_member(tenant, Role.ADMIN), tenant)
    teacher = make_member(tenant, Role.TEACHER)
    listed = client.get("/api/v1/members/")
    assert listed.status_code == 200
    assert teacher.email in {m["email"] for m in listed.data}
    for staff_role in ("teacher", "form_teacher", "bursar", "admin"):
        invite = {"email": f"{staff_role}@example.test", "role": staff_role}
        assert client.post("/api/v1/members/", invite, format="json").status_code == 403
    member_id = next(m["id"] for m in listed.data if m["email"] == teacher.email)
    assert client.post(f"/api/v1/members/{member_id}/deactivate/").status_code == 403
    assert client.post(f"/api/v1/members/{member_id}/resend_invite/").status_code == 403
    parent = client.post(
        "/api/v1/members/", {"email": "p@example.test", "role": "parent"}, format="json"
    )
    assert parent.status_code == 201, parent.content
    assert api(make_member(tenant, Role.TEACHER), tenant).get("/api/v1/members/").status_code == 403


def test_head_teacher_adds_and_blocks_teaching_and_support_staff(tenant, make_member, api):
    head_user = make_member(tenant, Role.PRINCIPAL, email="head@example.test")
    head = api(head_user, tenant)
    for staff_role in ("teacher", "form_teacher", "librarian", "warden", "driver"):
        invite = {"email": f"{staff_role}@example.test", "role": staff_role, "first_name": "New"}
        assert head.post("/api/v1/members/", invite, format="json").status_code == 201, staff_role
    # Leadership and finance roles stay with the proprietor.
    for staff_role in ("owner", "principal", "admin", "bursar"):
        invite = {"email": f"{staff_role}@example.test", "role": staff_role}
        assert head.post("/api/v1/members/", invite, format="json").status_code == 403, staff_role

    teacher = make_member(tenant, Role.TEACHER)
    owner = make_member(tenant, Role.OWNER)
    bursar = make_member(tenant, Role.BURSAR)
    by_user = {m.user_id: m.pk for m in Membership.objects.filter(tenant=tenant)}
    assert head.post(f"/api/v1/members/{by_user[teacher.pk]}/deactivate/").status_code == 200
    assert api(teacher, tenant).get("/api/v1/students/").status_code == 403  # blocked
    assert head.post(f"/api/v1/members/{by_user[teacher.pk]}/activate/").status_code == 200
    assert api(teacher, tenant).get("/api/v1/students/").status_code == 200  # unblocked
    for leader in (owner, bursar):
        assert head.post(f"/api/v1/members/{by_user[leader.pk]}/deactivate/").status_code == 403
    assert head.post(f"/api/v1/members/{by_user[head_user.pk]}/deactivate/").status_code in (
        400,
        403,
    )


def test_names_are_optional_when_inviting(tenant, make_member, api):
    """The invite form sends empty fields for names nobody typed in."""
    owner = api(make_member(tenant, Role.OWNER), tenant)
    blank = {"email": "nameless@example.test", "role": "teacher", "first_name": "", "last_name": ""}
    response = owner.post("/api/v1/members/", {**blank, "phone": ""}, format="json")
    assert response.status_code == 201, response.content


def test_nobody_gives_themselves_a_role(tenant, make_member, api):
    """Otherwise a head teacher could add themselves as a teacher and enter scores."""
    head_user = make_member(tenant, Role.PRINCIPAL, email="head@example.test")
    response = api(head_user, tenant).post(
        "/api/v1/members/", {"email": "Head@Example.test", "role": "teacher"}, format="json"
    )
    assert response.status_code == 403
    assert not Membership.objects.filter(user=head_user, role=Role.TEACHER).exists()


def test_me_lists_the_roles_each_person_may_give(tenant, make_member, api):
    def grantable(role):
        me = api(make_member(tenant, role), None).get("/api/v1/me/").data
        return me["schools"][0]["grantable_roles"]

    assert grantable(Role.PRINCIPAL) == [
        "teacher",
        "form_teacher",
        "librarian",
        "warden",
        "driver",
        "nurse",
        "store_keeper",
        "gate",
        "parent",
        "student",
    ]
    assert grantable(Role.ADMIN) == ["parent", "student"]
    assert grantable(Role.TEACHER) == []
    assert "principal" in grantable(Role.OWNER) and "bursar" in grantable(Role.OWNER)


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
