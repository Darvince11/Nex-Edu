from __future__ import annotations

import io

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.admissions.models import Application
from apps.students.models import Student, StudentGuardian
from control_plane.models import Membership, Role, User
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent

HEADER = "first_name,last_name,date_of_birth,gender,class,guardian_name,guardian_phone\n"


def _upload(client, content: bytes, name="students.csv", dry_run=False):
    return client.post(
        "/api/v1/students/import/",
        {"file": SimpleUploadedFile(name, content), "dry_run": "1" if dry_run else "0"},
        format="multipart",
    )


def test_csv_import_creates_students_and_guardians(tenant, make_member, api):
    client = api(make_member(tenant, Role.ADMIN), tenant)
    csv = HEADER + (
        "Kwame,Boateng,2013-04-02,M,JHS 1 A,Akua Boateng,024 412 3456\n"
        "Efua,Asante,05/09/2014,female,Basic 6A,Yaw Asante,+233 55 123 4567\n"
    )
    response = _upload(client, csv.encode())
    assert response.status_code == 201, response.data
    assert response.data["created"] == 2
    with tenant_context(tenant):
        kwame = Student.objects.get(first_name="Kwame")
        assert str(kwame.arm) == "JHS 1 A"
        assert kwame.admission_number.startswith("NXE/")
        guardian = StudentGuardian.objects.get(student=kwame)
        assert guardian.phone == "+233244123456"
        assert AuditEvent.objects.filter(action="student.bulk_imported").count() == 1


def test_import_with_any_bad_row_writes_nothing(tenant, make_member, api):
    client = api(make_member(tenant, Role.ADMIN), tenant)
    csv = HEADER + (
        "Kwame,Boateng,2013-04-02,M,JHS 1 A,,\nEfua,Asante,not-a-date,x,SHS 1 A,Yaw,0803 123 4567\n"
    )
    response = _upload(client, csv.encode())
    assert response.status_code == 400
    columns = {e["column"] for e in response.data["errors"]}
    assert {"date_of_birth", "gender", "class", "guardian_phone"} <= columns
    assert all(e["row"] == 3 for e in response.data["errors"])
    with tenant_context(tenant):
        assert Student.objects.count() == 0


def test_dry_run_validates_only(tenant, make_member, api):
    client = api(make_member(tenant, Role.ADMIN), tenant)
    response = _upload(
        client, (HEADER + "Kwame,Boateng,2013-04-02,M,JHS 1 A,,\n").encode(), dry_run=True
    )
    assert response.status_code == 200
    assert response.data["errors"] == []
    with tenant_context(tenant):
        assert Student.objects.count() == 0


def test_excel_import(tenant, make_member, api):
    wb = Workbook()
    ws = wb.active
    ws.append(["first_name", "last_name", "date_of_birth", "gender", "class"])
    ws.append(["Abena", "Owusu", "2012-01-15", "F", "JHS 2 A"])
    buffer = io.BytesIO()
    wb.save(buffer)
    client = api(make_member(tenant, Role.ADMIN), tenant)
    response = _upload(client, buffer.getvalue(), name="students.xlsx")
    assert response.status_code == 201, response.data


def test_teachers_cannot_import(tenant, make_member, api):
    client = api(make_member(tenant, Role.TEACHER), tenant)
    assert _upload(client, HEADER.encode()).status_code == 403


def test_add_guardian_requires_contact(tenant, make_member, make_student, api):
    student = make_student(tenant)
    client = api(make_member(tenant, Role.ADMIN), tenant)
    url = f"/api/v1/students/{student.pk}/guardians/"
    assert client.post(url, {"full_name": "No Contact"}, format="json").status_code == 400
    ok = client.post(url, {"full_name": "Akosua", "phone": "0244123456"}, format="json")
    assert ok.status_code == 201
    assert ok.data["phone"] == "+233244123456"


# --- Admissions -------------------------------------------------------------------------

PUBLIC_FORM = {
    "first_name": "Yaw",
    "last_name": "Mensah",
    "date_of_birth": "2014-02-01",
    "gender": "male",
    "guardian_name": "Ama Mensah",
    "guardian_phone": "0551234567",
    "guardian_email": "ama@example.test",
}


def _level_id(tenant, name):
    from apps.academics.models import ClassLevel

    with tenant_context(tenant):
        return ClassLevel.objects.get(name=name).pk


def test_public_admission_form(tenant, make_member, api):
    make_member(tenant, Role.ADMIN)
    client = api(None, tenant)
    options = client.get("/api/v1/public/admissions/")
    assert options.status_code == 200
    assert "JHS 1" in [lvl["name"] for lvl in options.data["levels"]]
    response = client.post(
        "/api/v1/public/admissions/",
        {**PUBLIC_FORM, "desired_level": _level_id(tenant, "JHS 1")},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["reference"].startswith("APP-")
    with tenant_context(tenant):
        application = Application.objects.get()
        assert application.source == "online"
        assert application.guardian_phone == "+233551234567"
        from apps.communication.models import Notification

        assert Notification.objects.filter(kind="admission").count() == 1


def test_public_form_honeypot_drops_bots(tenant, api):
    response = api(None, tenant).post(
        "/api/v1/public/admissions/",
        {**PUBLIC_FORM, "desired_level": _level_id(tenant, "JHS 1"), "website": "spam.example"},
        format="json",
    )
    assert response.status_code == 201
    with tenant_context(tenant):
        assert Application.objects.count() == 0


def test_public_form_needs_a_school(db, api):
    assert (
        api(None, None).post("/api/v1/public/admissions/", PUBLIC_FORM, format="json").status_code
        == 404
    )


def test_offer_then_enrol(tenant, make_member, api):
    admin = make_member(tenant, Role.ADMIN)
    client = api(admin, tenant)
    created = client.post(
        "/api/v1/admissions/applications/",
        {**PUBLIC_FORM, "desired_level": _level_id(tenant, "JHS 1")},
        format="json",
    )
    assert created.status_code == 201, created.data
    app_id = created.data["id"]
    from apps.academics.models import ClassArm

    with tenant_context(tenant):
        jhs1 = ClassArm.objects.get(level__name="JHS 1")
        jhs2 = ClassArm.objects.get(level__name="JHS 2")

    # Can't enrol before an offer; can't skip from rejected back.
    assert (
        client.post(
            f"/api/v1/admissions/applications/{app_id}/enrol/", {"arm": str(jhs1.pk)}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/v1/admissions/applications/{app_id}/change_status/",
            {"status": "offered"},
            format="json",
        ).status_code
        == 200
    )
    wrong_level = client.post(
        f"/api/v1/admissions/applications/{app_id}/enrol/", {"arm": str(jhs2.pk)}, format="json"
    )
    assert wrong_level.status_code == 400

    response = client.post(
        f"/api/v1/admissions/applications/{app_id}/enrol/", {"arm": str(jhs1.pk)}, format="json"
    )
    assert response.status_code == 200, response.data
    assert response.data["status"] == "enrolled"
    parent = User.objects.get(email="ama@example.test")
    assert Membership.objects.filter(user=parent, tenant=tenant, role="parent").exists()
    assert len(mail.outbox) == 1  # the parent's invitation
    with tenant_context(tenant):
        student = Student.objects.get(pk=response.data["student_id"])
        assert student.arm_id == jhs1.pk
        assert StudentGuardian.objects.get(student=student).guardian_user_id == parent.pk

    # The parent now sees exactly their child (parents don't need MFA).
    children = api(parent, tenant).get("/api/v1/students/").data["results"]
    assert [c["first_name"] for c in children] == ["Yaw"]
