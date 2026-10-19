"""Role permissions, record-level scoping, MFA enforcement, and fail-closed defaults."""

from __future__ import annotations

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.academics.models import ClassArm, TeachingAssignment
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context


def _arm(tenant, name):
    with tenant_context(tenant):
        return ClassArm.objects.select_related("level").get(level__name=name, name="A")


def _numbers(response):
    assert response.status_code == 200, response.content
    return sorted(s["admission_number"] for s in response.data["results"])


@pytest.fixture
def school(tenant, make_student):
    jhs1, jhs2 = _arm(tenant, "JHS 1"), _arm(tenant, "JHS 2")
    return {
        "jhs1": jhs1,
        "jhs2": jhs2,
        "s1": make_student(tenant, admission_number="S1", arm=jhs1, medical_notes="Asthma"),
        "s2": make_student(tenant, admission_number="S2", arm=jhs2),
    }


def test_school_wide_roles_see_everyone(tenant, school, make_member, api):
    for role in (Role.PRINCIPAL, Role.ADMIN, Role.BURSAR):
        assert _numbers(api(make_member(tenant, role), tenant).get("/api/v1/students/")) == [
            "S1",
            "S2",
        ]


def test_teacher_sees_only_assigned_arms(tenant, school, make_member, api):
    teacher = make_member(tenant, Role.TEACHER)
    with tenant_context(tenant):
        TeachingAssignment.objects.create(teacher_user_id=teacher.pk, arm=school["jhs1"])
    client = api(teacher, tenant)
    assert _numbers(client.get("/api/v1/students/")) == ["S1"]
    assert client.get(f"/api/v1/students/{school['s2'].pk}/").status_code == 404


def test_parent_sees_only_own_children(tenant, school, make_member, api):
    parent = make_member(tenant, Role.PARENT, mfa=False)
    with tenant_context(tenant):
        StudentGuardian.objects.create(student=school["s2"], guardian_user_id=parent.pk)
    assert _numbers(api(parent, tenant).get("/api/v1/students/")) == ["S2"]


def test_student_sees_only_self(tenant, make_member, make_student, api):
    pupil = make_member(tenant, Role.STUDENT, mfa=False)
    make_student(tenant, admission_number="ME", user_id=pupil.pk)
    make_student(tenant, admission_number="OTHER")
    assert _numbers(api(pupil, tenant).get("/api/v1/students/")) == ["ME"]


def test_sensitive_fields_need_permission(tenant, school, make_member, api):
    url = f"/api/v1/students/{school['s1'].pk}/"
    bursar = api(make_member(tenant, Role.BURSAR), tenant).get(url)
    assert "medical_notes" not in bursar.data
    principal = api(make_member(tenant, Role.PRINCIPAL), tenant).get(url)
    assert principal.data["medical_notes"] == "Asthma"


def test_write_needs_manage_permission(tenant, school, make_member, api):
    payload = {
        "admission_number": "NEW1",
        "first_name": "Chidi",
        "last_name": "Eze",
        "date_of_birth": "2013-05-02",
        "gender": "male",
    }
    teacher = api(make_member(tenant, Role.TEACHER), tenant)
    assert teacher.post("/api/v1/students/", payload, format="json").status_code == 403
    admin = api(make_member(tenant, Role.ADMIN), tenant)
    response = admin.post("/api/v1/students/", payload, format="json")
    assert response.status_code == 201, response.content


def test_staff_without_mfa_are_blocked(tenant, school, make_member, api):
    teacher = make_member(tenant, Role.ADMIN, mfa=False)
    response = api(teacher, tenant).get("/api/v1/students/")
    assert response.status_code == 403
    assert response.data["code"] == "mfa_enrollment_required"


def test_unauthenticated_requests_are_rejected(tenant, api):
    assert api(None, tenant).get("/api/v1/students/").status_code in (401, 403)


def test_platform_superuser_gets_no_implicit_school_access(tenant, school, api):
    from control_plane.models import User

    root = User.objects.create_superuser("root@example.test", "x" * 16)
    assert api(root, tenant).get("/api/v1/students/").status_code == 403


def _iter_views(resolver, prefix=""):
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            yield from _iter_views(pattern, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern):
            yield prefix + str(pattern.pattern), pattern.callback


def test_every_tenant_api_view_declares_permissions():
    """Authorization matrix guard: every action of every endpoint must map to a
    permission, or the view must be explicitly marked public. Fails CI otherwise."""
    from core.permissions import required_permission_for

    missing = []
    for route, callback in _iter_views(get_resolver()):
        view = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        if not route.startswith("api/v1/") or view is None:
            continue
        if getattr(view, "public_endpoint", False) or getattr(view, "tenant_scoped", True) is False:
            continue
        actions = getattr(callback, "actions", None)
        if actions:  # viewset: check each routed action
            for method, action_name in actions.items():
                probe = type(
                    "Probe",
                    (),
                    {"action": action_name, "required_permissions": view.required_permissions},
                )
                if required_permission_for(probe, method.upper()) is None:
                    missing.append(f"{route} {method.upper()} ({action_name})")
        else:
            for method in ("get", "post", "put", "patch", "delete"):
                if (
                    hasattr(view, method)
                    and method in view.http_method_names
                    and required_permission_for(view, method.upper()) is None
                ):
                    missing.append(f"{route} {method.upper()}")
    assert missing == []


def test_public_endpoints_are_exactly_the_expected_ones():
    public = sorted(
        route
        for route, callback in _iter_views(get_resolver())
        if getattr(
            getattr(callback, "view_class", None) or getattr(callback, "cls", None),
            "public_endpoint",
            False,
        )
    )
    assert public == [
        "api/v1/public/admissions/",
        "api/v1/webhooks/flutterwave/",
        "api/v1/webhooks/paystack/",
    ]
