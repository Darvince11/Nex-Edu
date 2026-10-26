"""What teachers may do for their own classes, and what the head teacher may not do.

Class (form) teachers add pupils to their own class and prepare its report cards.
Subject teachers only view registers and mark attendance for pupils. Any teacher
keeps the timetable of the classes they teach.
"""

from __future__ import annotations

import pytest

from apps.students.models import Student
from control_plane.models import Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

PUPIL = {
    "first_name": "Chidi",
    "last_name": "Eze",
    "date_of_birth": "2013-05-02",
    "gender": "male",
}


@pytest.fixture
def class_teacher(campus, make_member, assign, api):
    user = make_member(campus.tenant, Role.FORM_TEACHER)
    assign(user, campus.jhs1, form=True)
    return api(user, campus.tenant)


@pytest.fixture
def subject_teacher(campus, make_member, assign, api):
    user = make_member(campus.tenant, Role.TEACHER)
    assign(user, campus.jhs1, campus.subjects["MTH"])
    return api(user, campus.tenant)


def test_class_teacher_adds_pupils_to_own_class_only(campus, class_teacher):
    mine = class_teacher.post(
        "/api/v1/students/", {**PUPIL, "arm": str(campus.jhs1.pk)}, format="json"
    )
    assert mine.status_code == 201, mine.content
    # The pupil lands in the class straight away, so the register shows them.
    with tenant_context(campus.tenant):
        assert Student.objects.get(pk=mine.data["id"]).arm_id == campus.jhs1.pk
    register = class_teacher.get(f"/api/v1/students/?arm={campus.jhs1.pk}")
    assert mine.data["id"] in {s["id"] for s in register.data["results"]}

    other = class_teacher.post(
        "/api/v1/students/", {**PUPIL, "arm": str(campus.jhs2.pk)}, format="json"
    )
    assert other.status_code == 403
    no_class = class_teacher.post("/api/v1/students/", PUPIL, format="json")
    assert no_class.status_code == 403


def test_class_teachers_can_list_their_own_class(campus, class_teacher, subject_teacher):
    assert [a["id"] for a in class_teacher.get("/api/v1/academics/arms/?mine=form").data] == [
        str(campus.jhs1.pk)
    ]
    assert subject_teacher.get("/api/v1/academics/arms/?mine=form").data == []
    assert len(subject_teacher.get("/api/v1/academics/arms/?mine=1").data) == 1


def test_class_teacher_adds_guardians_for_own_class_only(campus, class_teacher, make_student):
    mine = make_student(campus.tenant, arm=campus.jhs1)
    theirs = make_student(campus.tenant, arm=campus.jhs2)
    guardian = {"full_name": "Ama Eze", "phone": "024 412 3456", "relationship": "mother"}
    ok = class_teacher.post(f"/api/v1/students/{mine.pk}/guardians/", guardian, format="json")
    assert ok.status_code == 201, ok.content
    # Another class's pupil isn't even visible to them.
    refused = class_teacher.post(
        f"/api/v1/students/{theirs.pk}/guardians/", guardian, format="json"
    )
    assert refused.status_code in (403, 404)


def test_subject_teachers_cannot_add_pupils(campus, subject_teacher):
    response = subject_teacher.post(
        "/api/v1/students/", {**PUPIL, "arm": str(campus.jhs1.pk)}, format="json"
    )
    assert response.status_code == 403


def _period(campus, arm, **extra):
    return {
        "term": campus.term.pk,
        "arm": str(arm.pk),
        "subject": campus.subjects["MTH"].pk,
        "weekday": 2,
        "starts_at": "10:00",
        "ends_at": "10:40",
        **extra,
    }


def test_teachers_keep_the_timetable_of_classes_they_teach(campus, subject_teacher):
    url = "/api/v1/academics/periods/"
    created = subject_teacher.post(url, _period(campus, campus.jhs1), format="json")
    assert created.status_code == 201, created.content
    period = f"{url}{created.data['id']}/"
    assert (
        subject_teacher.patch(period, {"starts_at": "10:40", "ends_at": "11:20"}, format="json")
    ).status_code == 200
    # Not another class, and a period can't be moved into one either.
    assert subject_teacher.post(url, _period(campus, campus.jhs2), format="json").status_code == 403
    assert (
        subject_teacher.patch(period, {"arm": str(campus.jhs2.pk)}, format="json").status_code
        == 403
    )
    assert subject_teacher.delete(period).status_code == 204


def test_teachers_cannot_change_other_classes_periods(campus, subject_teacher, make_member, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    theirs = admin.post(
        "/api/v1/academics/periods/", _period(campus, campus.jhs2), format="json"
    ).data["id"]
    url = f"/api/v1/academics/periods/{theirs}/"
    assert subject_teacher.patch(url, {"weekday": 3}, format="json").status_code == 403
    assert subject_teacher.delete(url).status_code == 403


def test_class_teacher_prepares_report_cards_for_own_class_only(
    campus, class_teacher, subject_teacher, make_student
):
    make_student(campus.tenant, arm=campus.jhs1)
    make_student(campus.tenant, arm=campus.jhs2)
    for arm, allowed in ((campus.jhs1, True), (campus.jhs2, False)):
        body = {"arm": str(arm.pk), "term": campus.term.pk}
        for step in ("compute", "publish"):
            response = class_teacher.post(
                f"/api/v1/assessments/results/{step}/", body, format="json"
            )
            # Computing an empty class may fail validation (400); what matters is access.
            assert (response.status_code != 403) is allowed, (step, arm, response.content)
    body = {"arm": str(campus.jhs1.pk), "term": campus.term.pk}
    assert (
        subject_teacher.post("/api/v1/assessments/results/compute/", body, format="json")
    ).status_code == 403


def test_head_teacher_sets_up_grading_but_enters_no_scores(campus, make_member, api):
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    band = {"grade": "X", "min_score": "0", "max_score": "1", "remark": "Test"}
    assert head.get("/api/v1/assessments/grade-bands/").status_code == 200
    assert head.post("/api/v1/assessments/grade-bands/", band, format="json").status_code != 403
    # The score-entry grid is closed to them; they see results on report cards.
    sheet = head.get(
        "/api/v1/assessments/scores/",
        {"arm": str(campus.jhs1.pk), "subject": campus.subjects["ENG"].pk, "term": campus.term.pk},
    )
    assert sheet.status_code == 403
    entry = head.post(
        "/api/v1/assessments/scores/",
        {
            "arm": str(campus.jhs1.pk),
            "subject": campus.subjects["ENG"].pk,
            "term": campus.term.pk,
            "rows": [],
        },
        format="json",
    )
    assert entry.status_code == 403
