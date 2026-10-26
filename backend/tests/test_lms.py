"""Homework and materials: who sets, who hands in, who marks, who sees."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.communication.models import Notification
from apps.students.models import Student, StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/lms/"


@pytest.fixture
def school(campus, make_member, make_student, api, assign):
    set_active(tenant=campus.tenant, code="lms", active=True, request=None)
    maths_user = make_member(campus.tenant, Role.TEACHER)
    assign(maths_user, campus.jhs1, campus.subjects["MTH"])
    other_user = make_member(campus.tenant, Role.TEACHER)
    assign(other_user, campus.jhs2, campus.subjects["MTH"])
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    classmate = make_student(campus.tenant, arm=campus.jhs1)
    pupil_user = make_member(campus.tenant, Role.STUDENT, mfa=False)
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        Student.objects.filter(pk=pupil.pk).update(user_id=pupil_user.pk)
        StudentGuardian.objects.create(student=pupil, guardian_user_id=parent_user.pk)
    return {
        "maths": api(maths_user, campus.tenant),
        "other": api(other_user, campus.tenant),
        "pupil": api(pupil_user, campus.tenant),
        "pupil_user": pupil_user,
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "child": pupil,
        "classmate": classmate,
    }


def _set(client, campus, **extra):
    return client.post(
        f"{URL}homework/",
        {
            "arm": str(campus.jhs1.pk),
            "subject": campus.subjects["MTH"].pk,
            "title": "Fractions exercise 4",
            "instructions": "Questions 1 to 10.",
            "due_on": (timezone.localdate() + dt.timedelta(days=3)).isoformat(),
            "max_score": 10,
            **extra,
        },
        format="json",
    )


def test_teachers_set_homework_only_for_what_they_teach(campus, school):
    made = _set(school["maths"], campus)
    assert made.status_code == 201, made.content
    assert _set(school["other"], campus).status_code == 403
    assert school["other"].get(f"{URL}homework/").json() == []
    with tenant_context(campus.tenant):
        assert Notification.objects.filter(
            recipient_user_id=school["pupil_user"].pk, kind="homework"
        ).exists()
        assert Notification.objects.filter(
            recipient_user_id=school["parent_user"].pk, kind="homework"
        ).exists()


def test_pupils_hand_in_and_teachers_mark(campus, school, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    homework = _set(school["maths"], campus).json()["id"]
    empty = school["pupil"].post(f"{URL}homework/{homework}/submit/", {}, format="multipart")
    assert empty.status_code == 400
    work = SimpleUploadedFile("answers.pdf", b"%PDF-1.4 answers", content_type="application/pdf")
    handed = school["pupil"].post(
        f"{URL}homework/{homework}/submit/",
        {"text": "My answers attached.", "file": work},
        format="multipart",
    )
    assert handed.status_code == 201, handed.content
    assert handed.json()["late"] is False and handed.json()["has_file"] is True
    bad = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
    assert (
        school["pupil"]
        .post(f"{URL}homework/{homework}/submit/", {"file": bad}, format="multipart")
        .status_code
        == 400
    )

    sheet = school["maths"].get(f"{URL}homework/{homework}/submissions/").json()
    assert len(sheet) == 2  # the whole class, handed in or not
    submission = next(r["submission"] for r in sheet if r["submission"])
    assert (
        school["other"].post(f"{URL}submissions/{submission['id']}/mark/", {"score": 8}).status_code
        == 404
    )
    over = school["maths"].post(
        f"{URL}submissions/{submission['id']}/mark/", {"score": 11}, format="json"
    )
    assert over.status_code == 400
    marked = school["maths"].post(
        f"{URL}submissions/{submission['id']}/mark/",
        {"score": 8, "feedback": "Good work."},
        format="json",
    )
    assert marked.json()["score"] == 8
    # Once marked, it can't be changed by the pupil.
    again = school["pupil"].post(
        f"{URL}homework/{homework}/submit/", {"text": "v2"}, format="multipart"
    )
    assert again.status_code == 400

    seen = school["parent"].get(f"{URL}homework/").json()
    assert seen[0]["mine"][0]["score"] == 8 and seen[0]["mine"][0]["feedback"] == "Good work."
    assert (
        school["parent"].post(f"{URL}homework/{homework}/submit/", {"text": "x"}).status_code == 403
    )


def test_late_work_is_flagged(campus, school):
    homework = _set(
        school["maths"], campus, due_on=(timezone.localdate() - dt.timedelta(days=1)).isoformat()
    )
    handed = school["pupil"].post(
        f"{URL}homework/{homework.json()['id']}/submit/",
        {"text": "Sorry it's late."},
        format="multipart",
    )
    assert handed.json()["late"] is True


def test_materials_are_shared_with_the_class(campus, school):
    shared = school["maths"].post(
        f"{URL}materials/",
        {
            "arm": str(campus.jhs1.pk),
            "subject": campus.subjects["MTH"].pk,
            "title": "Fractions video",
            "link": "https://example.org/fractions",
        },
        format="json",
    )
    assert shared.status_code == 201, shared.content
    assert [m["title"] for m in school["pupil"].get(f"{URL}materials/").json()] == [
        "Fractions video"
    ]
    assert school["other"].get(f"{URL}materials/").json() == []
    nothing = school["maths"].post(
        f"{URL}materials/",
        {"arm": str(campus.jhs1.pk), "subject": campus.subjects["MTH"].pk, "title": "Empty"},
        format="json",
    )
    assert nothing.status_code == 400
