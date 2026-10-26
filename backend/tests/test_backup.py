"""Single-school backup and restore: a copy for checking, and in place after a mistake."""

from __future__ import annotations

import pytest
from django.core.files.storage import default_storage

from apps.students.models import Student
from apps.students.selectors import find_by_national_id
from control_plane import backup
from control_plane.models import Membership, Role, Tenant
from control_plane.tenancy import tenant_context
from core.files import save_tenant_file

pytestmark = pytest.mark.django_db


@pytest.fixture
def school(campus, make_student, make_member):
    owner = make_member(campus.tenant, Role.OWNER)
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Adwoa")
    with tenant_context(campus.tenant):
        from apps.students.services import _set_national_id_index

        pupil.national_id = "GHA-123456789-0"
        _set_national_id_index(pupil)
        pupil.save()
        key = save_tenant_file("reports/adwoa.pdf", b"%PDF report")
    return {"tenant": campus.tenant, "pupil": pupil, "owner": owner, "file": key}


def test_a_copy_matches_and_is_re_encrypted_with_its_own_key(school):
    tenant = school["tenant"]
    zip_key = backup.backup(tenant)
    copy = backup.restore_copy(zip_key, slug="greenfield-copy", name="Copy")
    assert copy.status == Tenant.Status.PROVISIONING  # nobody can open it
    assert backup.counts(copy) == backup.counts(tenant)
    with tenant_context(copy):
        restored = Student.objects.get(first_name="Adwoa")
        assert restored.national_id == "GHA-123456789-0"
        assert find_by_national_id("GHA-123456789-0") == restored  # index redone for the new key
    with tenant_context(tenant):
        original_index = Student.objects.get(pk=school["pupil"].pk).national_id_bidx
    assert restored.national_id_bidx != original_index
    assert default_storage.exists("tenants/greenfield-copy/reports/adwoa.pdf")

    backup.discard_copy(copy)
    assert not Tenant.objects.filter(slug="greenfield-copy").exists()
    assert not default_storage.exists("tenants/greenfield-copy/reports/adwoa.pdf")


def test_in_place_restore_brings_back_deleted_records_and_keeps_sign_ins(school):
    tenant = school["tenant"]
    zip_key = backup.backup(tenant)
    with tenant_context(tenant):
        Student.objects.filter(pk=school["pupil"].pk).delete()  # the mistake
    backup.restore_in_place(tenant, zip_key)
    tenant.refresh_from_db()
    assert tenant.status == Tenant.Status.ACTIVE
    with tenant_context(tenant):
        assert Student.objects.get(pk=school["pupil"].pk).national_id == "GHA-123456789-0"
    assert Membership.objects.filter(user=school["owner"], tenant=tenant).exists()


def test_a_backup_of_another_school_is_refused(school, other_tenant):
    zip_key = backup.backup(school["tenant"])
    with pytest.raises(ValueError, match="not"):
        backup.restore_in_place(other_tenant, zip_key)


def test_the_drill_passes(school):
    result = backup.drill(school["tenant"])
    assert result["passed"] and result["records"] > 0 and not result["mismatched"]
