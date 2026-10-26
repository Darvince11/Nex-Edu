"""Online tests: writing, sitting once in time, marking, releasing."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.exams.models import Attempt
from apps.students.models import Student, StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/exams/tests/"


@pytest.fixture
def school(campus, make_member, make_student, api, assign):
    set_active(tenant=campus.tenant, code="lms", active=True, request=None)
    set_active(tenant=campus.tenant, code="online_exams", active=True, request=None)
    teacher_user = make_member(campus.tenant, Role.TEACHER)
    assign(teacher_user, campus.jhs1, campus.subjects["MTH"])
    pupil = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    pupil_user = make_member(campus.tenant, Role.STUDENT, mfa=False)
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    other_user = make_member(campus.tenant, Role.STUDENT, mfa=False)
    other = make_student(campus.tenant, arm=campus.jhs2)
    with tenant_context(campus.tenant):
        Student.objects.filter(pk=pupil.pk).update(user_id=pupil_user.pk)
        Student.objects.filter(pk=other.pk).update(user_id=other_user.pk)
        StudentGuardian.objects.create(student=pupil, guardian_user_id=parent_user.pk)
    teacher = api(teacher_user, campus.tenant)
    now = timezone.now()
    test = teacher.post(
        URL,
        {
            "arm": str(campus.jhs1.pk),
            "subject": campus.subjects["MTH"].pk,
            "title": "Fractions quiz",
            "opens_at": (now - dt.timedelta(minutes=5)).isoformat(),
            "closes_at": (now + dt.timedelta(hours=1)).isoformat(),
            "minutes": 20,
        },
        format="json",
    )
    assert test.status_code == 201, test.content
    test_id = test.json()["id"]
    questions = teacher.put(
        f"{URL}{test_id}/questions/",
        [
            {
                "kind": "choice",
                "text": "1/2 + 1/4 = ?",
                "options": ["3/4", "2/6", "1/8"],
                "answer": 0,
                "marks": 2,
            },
            {"kind": "true_false", "text": "1/3 > 1/2", "answer": 1, "marks": 1},
            {"kind": "short", "text": "Explain how you add fractions.", "marks": 3},
        ],
        format="json",
    )
    assert questions.status_code == 200, questions.content
    return {
        "teacher": teacher,
        "pupil": api(pupil_user, campus.tenant),
        "other": api(other_user, campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "test": test_id,
        "questions": [q["id"] for q in questions.json()],
    }


def test_pupils_sit_once_without_seeing_answers(campus, school):
    assert school["pupil"].get(URL).json() == []  # not published yet
    assert school["teacher"].post(f"{URL}{school['test']}/publish/").status_code == 200
    started = school["pupil"].post(f"{URL}{school['test']}/start/").json()
    assert all("answer" not in q for q in started["questions"])
    assert school["other"].post(f"{URL}{school['test']}/start/").status_code == 404  # another class
    q1, q2, q3 = (str(i) for i in school["questions"])
    school["pupil"].post(f"{URL}{school['test']}/save/", {"answers": {q1: 0}}, format="json")
    done = school["pupil"].post(
        f"{URL}{school['test']}/submit/",
        {"answers": {q1: 0, q2: 0, q3: "Same denominator."}},
        format="json",
    )
    assert done.json()["status"] == "submitted"  # a short answer waits for the teacher
    assert school["pupil"].post(f"{URL}{school['test']}/start/").status_code == 400  # only once
    # Changing questions after pupils start is refused.
    assert (
        school["teacher"].put(f"{URL}{school['test']}/questions/", [], format="json").status_code
        == 400
    )

    results = school["teacher"].get(f"{URL}{school['test']}/results/").json()
    mine = next(r for r in results if r["attempt"])
    assert mine["score"] == 2  # 2 for q1, 0 for the wrong true/false
    assert (
        school["teacher"].post(f"{URL}{school['test']}/release/").status_code == 400
    )  # still to mark
    marked = school["teacher"].post(
        f"{URL}{school['test']}/attempts/{mine['attempt']}/mark/",
        {"awarded": {q3: 2}},
        format="json",
    )
    assert marked.json() == {"score": 4, "status": "marked"}
    assert school["parent"].get(f"{URL}mine/").json() == []
    school["teacher"].post(f"{URL}{school['test']}/release/")
    assert school["parent"].get(f"{URL}mine/").json()[0]["score"] == 4


def test_time_runs_out(campus, school):
    school["teacher"].post(f"{URL}{school['test']}/publish/")
    school["pupil"].post(f"{URL}{school['test']}/start/")
    q1 = str(school["questions"][0])
    with tenant_context(campus.tenant):
        Attempt.objects.update(started_at=timezone.now() - dt.timedelta(minutes=30))
    late = school["pupil"].post(f"{URL}{school['test']}/save/", {"answers": {q1: 0}}, format="json")
    assert late.status_code == 400
    # Handing in late keeps only what was saved in time (nothing here).
    school["pupil"].post(f"{URL}{school['test']}/submit/", {"answers": {q1: 0}}, format="json")
    with tenant_context(campus.tenant):
        assert Attempt.objects.get().answers == {}


def test_bad_questions_are_refused(campus, school):
    bad = school["teacher"].put(
        f"{URL}{school['test']}/questions/",
        [{"kind": "choice", "text": "x", "options": ["a"], "answer": 0}],
        format="json",
    )
    assert bad.status_code == 400
