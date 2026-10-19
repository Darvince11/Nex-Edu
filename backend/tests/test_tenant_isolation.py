"""A school's data must never be reachable from another school."""

from __future__ import annotations

import pytest

from apps.students.models import Student
from control_plane.models import Role, Tenant
from control_plane.tenancy import CrossTenantAccess, TenantContextMissing, tenant_context


def test_each_school_has_its_own_database(tenant, other_tenant):
    assert tenant.db_alias != other_tenant.db_alias
    assert tenant.db_name != other_tenant.db_name


def test_tenant_models_fail_closed_without_a_school(tenant):
    with pytest.raises(TenantContextMissing):
        Student.objects.count()


def test_rows_are_invisible_across_schools(tenant, other_tenant, make_student):
    make_student(tenant, admission_number="A1")
    with tenant_context(tenant):
        assert Student.objects.count() == 1
    with tenant_context(other_tenant):
        assert Student.objects.count() == 0


def test_object_from_one_school_cannot_be_saved_into_another(tenant, other_tenant, make_student):
    student = make_student(tenant)
    with tenant_context(tenant):
        loaded = Student.objects.get(pk=student.pk)
    with tenant_context(other_tenant), pytest.raises(CrossTenantAccess):
        loaded.save()


def test_api_rejects_users_from_another_school(
    tenant, other_tenant, make_member, make_student, api
):
    make_student(tenant)
    outsider = make_member(other_tenant, Role.PRINCIPAL)
    response = api(outsider, tenant).get("/api/v1/students/")
    assert response.status_code == 403


def test_member_of_two_schools_sees_only_selected_school(
    tenant, other_tenant, make_member, make_student, api
):
    make_student(tenant, admission_number="G-1")
    make_student(other_tenant, admission_number="R-1")
    user = make_member(tenant, Role.ADMIN)
    from control_plane.models import Membership

    Membership.objects.create(user=user, tenant=other_tenant, role=Role.ADMIN)

    numbers = [
        s["admission_number"] for s in api(user, tenant).get("/api/v1/students/").data["results"]
    ]
    assert numbers == ["G-1"]
    numbers = [
        s["admission_number"]
        for s in api(user, other_tenant).get("/api/v1/students/").data["results"]
    ]
    assert numbers == ["R-1"]


def test_unknown_and_suspended_schools(tenant, make_member, api):
    user = make_member(tenant, Role.ADMIN)
    client = api(user, None)
    assert client.get("/api/v1/students/", HTTP_X_TENANT="nope-school").status_code == 404

    Tenant.objects.filter(pk=tenant.pk).update(status=Tenant.Status.SUSPENDED)
    response = api(user, tenant).get("/api/v1/students/")
    assert response.status_code == 403
    assert response.json()["code"] == "tenant_unavailable"


def test_subdomain_resolution(tenant, make_member, settings):
    from rest_framework.test import APIClient

    settings.ALLOWED_HOSTS = [".nexedu.test"]
    settings.TENANT_BASE_DOMAIN = "nexedu.test"
    user = make_member(tenant, Role.ADMIN)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1/students/", HTTP_HOST="greenfield.nexedu.test").status_code == 200


def test_tenant_responses_are_never_cached(tenant, make_member, api):
    response = api(make_member(tenant, Role.ADMIN), tenant).get("/api/v1/students/")
    assert "no-store" in response["Cache-Control"]
    assert "X-Tenant" in response["Vary"]


def test_school_database_contains_no_control_plane_tables(tenant):
    from django.db import connections

    with tenant_context(tenant):
        tables = set(connections[tenant.db_alias].introspection.table_names())
    assert "control_plane_user" not in tables
    assert "students_student" in tables
