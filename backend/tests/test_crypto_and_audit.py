from __future__ import annotations

import pytest
from django.db import connections

from apps.students.models import Student
from apps.students.selectors import find_by_national_id
from control_plane.models import Role
from control_plane.tenancy import tenant_context
from core.audit.models import AppendOnlyError, AuditEvent
from core.audit.services import record_event, verify_chain
from core.crypto import DecryptionError, blind_index, decrypt_value, encrypt_value


def _raw(tenant, sql, params=()):
    with connections[tenant.db_alias].cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


def test_sensitive_fields_are_encrypted_at_rest(tenant, make_student):
    student = make_student(tenant, medical_notes="Sickle cell trait", national_id="GHA-123456789-0")
    with tenant_context(tenant):
        ((notes, national_id),) = _raw(
            tenant,
            "SELECT medical_notes, national_id FROM students_student WHERE id = %s",
            [student.pk.hex],
        )
        assert notes.startswith("v1.") and "Sickle" not in notes
        assert national_id.startswith("v1.") and "123456789" not in national_id
        assert Student.objects.get(pk=student.pk).medical_notes == "Sickle cell trait"


def test_ciphertext_is_bound_to_school_and_column(tenant, other_tenant):
    token = encrypt_value("secret", tenant=tenant, context="students.student.national_id")
    assert decrypt_value(token, tenant=tenant, context="students.student.national_id") == "secret"
    with pytest.raises(DecryptionError):
        decrypt_value(token, tenant=other_tenant, context="students.student.national_id")
    with pytest.raises(DecryptionError):
        decrypt_value(token, tenant=tenant, context="students.student.medical_notes")


def test_blind_index_lookup(tenant, other_tenant, make_student):
    student = make_student(tenant, national_id="gha-123456789-0")
    with tenant_context(tenant):
        assert find_by_national_id("GHA 123456789-0").pk == student.pk
    a = blind_index("GHA-123456789-0", tenant=tenant, context="c")
    b = blind_index("GHA-123456789-0", tenant=other_tenant, context="c")
    assert a != b


def test_student_changes_are_audited_without_leaking_secrets(
    tenant, make_member, make_student, api
):
    admin = make_member(tenant, Role.ADMIN)
    student = make_student(tenant, medical_notes="Epilepsy")
    response = api(admin, tenant).patch(
        f"/api/v1/students/{student.pk}/",
        {"medical_notes": "Epilepsy, controlled", "first_name": "Adaeze"},
        format="json",
        HTTP_X_CHANGE_REASON="Parent update",
    )
    assert response.status_code == 200, response.content
    with tenant_context(tenant):
        event = AuditEvent.objects.get(action="student.updated")
        assert event.actor_id == admin.pk
        assert event.reason == "Parent update"
        assert event.after["first_name"] == "Adaeze"
        assert "Epilepsy" not in str(event.before) + str(event.after)


def test_audit_chain_detects_tampering(tenant):
    with tenant_context(tenant):
        for i in range(5):
            record_event(action=f"test.{i}")
        assert verify_chain().valid

        _raw(tenant, "UPDATE audit_auditevent SET action = 'forged' WHERE seq = 3")
        report = verify_chain()
        assert not report.valid
        assert report.first_bad_seq == 3


def test_audit_chain_detects_deleted_tail(tenant):
    with tenant_context(tenant):
        for i in range(3):
            record_event(action=f"test.{i}")
        _raw(tenant, "DELETE FROM audit_auditevent WHERE seq = 3")
        assert verify_chain().reason == "events removed from the end"


def test_audit_events_are_append_only_in_the_orm(tenant):
    with tenant_context(tenant):
        event = record_event(action="test")
        event.action = "changed"
        with pytest.raises(AppendOnlyError):
            event.save()
        with pytest.raises(AppendOnlyError):
            event.delete()
        with pytest.raises(AppendOnlyError):
            AuditEvent.objects.all().update(action="x")
        with pytest.raises(AppendOnlyError):
            AuditEvent.objects.all().delete()


def test_audit_api(tenant, make_member, make_student, api):
    make_student(tenant)
    principal = api(make_member(tenant, Role.PRINCIPAL), tenant)
    assert principal.get("/api/v1/audit/verify/").data["valid"] is True
    assert principal.get("/api/v1/audit/events/").data["results"][0]["action"] == "student.created"
    teacher = api(make_member(tenant, Role.TEACHER), tenant)
    assert teacher.get("/api/v1/audit/events/").status_code == 403


def test_audit_export_to_s3(tenant, settings):
    from core.audit.tasks import export_new_events

    settings.AUDIT_EXPORT_BUCKET = "audit-bucket"

    class FakeS3:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)

    s3 = FakeS3()
    with tenant_context(tenant):
        record_event(action="a")
        record_event(action="b")
    assert export_new_events(tenant, s3) == 2
    assert export_new_events(tenant, s3) == 0
    assert s3.calls[0]["Key"].startswith("audit/greenfield/")
    assert s3.calls[0]["ServerSideEncryption"] == "aws:kms"
