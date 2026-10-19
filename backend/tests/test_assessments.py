from __future__ import annotations

from decimal import Decimal

import pytest

from apps.assessments.models import AssessmentComponent, ReportCard, Score
from apps.assessments.services import bece_aggregate, competition_rank, ordinal
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.tenancy import tenant_context
from core.audit.models import AuditEvent


def _components(tenant):
    with tenant_context(tenant):
        return {c.code: c.pk for c in AssessmentComponent.objects.all()}


def _enter(client, campus, arm, subject, rows):
    """rows: {student: (class_score, exam)}"""
    comps = _components(campus.tenant)
    entries = []
    for student, (cs, exam) in rows.items():
        entries += [
            {"student": str(student.pk), "component": comps["CS"], "score": cs},
            {"student": str(student.pk), "component": comps["EXAM"], "score": exam},
        ]
    return client.post(
        "/api/v1/assessments/scores/",
        {
            "arm": str(arm.pk),
            "subject": campus.subjects[subject].pk,
            "term": campus.term.pk,
            "entries": entries,
        },
        format="json",
    )


def test_ranking_helpers():
    assert competition_rank({"a": Decimal(90), "b": Decimal(90), "c": Decimal(70)}) == {
        "a": 1,
        "b": 1,
        "c": 3,
    }
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
        "101st",
    ]
    lines = [
        {"code": c, "points": p}
        for c, p in [
            ("ENG", 1),
            ("MTH", 2),
            ("SCI", 1),
            ("SOC", 3),
            ("RME", 4),
            ("ICT", 1),
            ("FRE", 9),
        ]
    ]
    assert bece_aggregate(lines) == 1 + 2 + 1 + 3 + 1 + 4  # best two electives: ICT 1, RME 4
    assert bece_aggregate(lines[1:]) is None  # English missing


def test_teacher_enters_scores_only_for_own_subject(campus, make_member, make_student, assign, api):
    teacher = make_member(campus.tenant, Role.TEACHER)
    assign(teacher, campus.jhs1, campus.subjects["MTH"])
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    client = api(teacher, campus.tenant)
    assert _enter(client, campus, campus.jhs1, "MTH", {s1: (25, 60)}).status_code == 200
    assert _enter(client, campus, campus.jhs1, "ENG", {s1: (25, 60)}).status_code == 403
    sheet = client.get(
        f"/api/v1/assessments/scores/?arm={campus.jhs1.pk}"
        f"&subject={campus.subjects['MTH'].pk}&term={campus.term.pk}"
    )
    assert sheet.status_code == 200
    assert sheet.data["rows"][0]["scores"][str(_components(campus.tenant)["CS"])] == "25.00"


def test_scores_above_component_maximum_are_rejected(campus, make_member, make_student, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    response = _enter(admin, campus, campus.jhs1, "MTH", {s1: (31, 60)})  # class score is /30
    assert response.status_code == 400
    with tenant_context(campus.tenant):
        assert Score.objects.count() == 0


@pytest.fixture
def results(campus, make_member, make_student, api):
    """Three JHS 1 students, four core subjects + two electives, then computed."""
    principal = make_member(campus.tenant, Role.PRINCIPAL)
    client = api(principal, campus.tenant)
    a = make_student(campus.tenant, arm=campus.jhs1, first_name="Akua")
    b = make_student(campus.tenant, arm=campus.jhs1, first_name="Bright")
    c = make_student(campus.tenant, arm=campus.jhs1, first_name="Comfort")
    scores = {  # same totals for Akua and Bright, so they tie
        "ENG": {a: (28, 60), b: (28, 60), c: (15, 30)},
        "MTH": {a: (25, 55), b: (25, 55), c: (10, 30)},
        "SCI": {a: (27, 60), b: (27, 60), c: (12, 25)},
        "SOC": {a: (26, 50), b: (26, 50), c: (20, 40)},
        "RME": {a: (29, 65), b: (29, 65), c: (25, 50)},
        "ICT": {a: (20, 50), b: (20, 50), c: (18, 50)},
    }
    for subject, rows in scores.items():
        assert _enter(client, campus, campus.jhs1, subject, rows).status_code == 200
    computed = client.post(
        "/api/v1/assessments/results/compute/",
        {"arm": str(campus.jhs1.pk), "term": campus.term.pk},
        format="json",
    )
    assert computed.status_code == 200, computed.data
    return {"client": client, "a": a, "b": b, "c": c, "principal": principal}


def test_results_totals_grades_positions_and_aggregate(campus, results):
    with tenant_context(campus.tenant):
        cards = {str(card.student_id): card for card in ReportCard.objects.all()}
    akua, bright, comfort = (cards[str(results[k].pk)] for k in "abc")
    eng = next(line for line in akua.lines if line["code"] == "ENG")
    assert eng["total"] == "88.00"
    assert eng["grade"] == "1"  # BECE grade 1 is 80-100
    assert eng["position"] == "1st"
    assert eng["class_highest"] == "88.00"
    assert eng["class_lowest"] == "45.00"
    assert akua.position == bright.position == 1
    assert comfort.position == 3
    assert akua.class_size == 3
    # Akua: ENG 88(1) MTH 80(1) SCI 87(1) SOC 76(2) + best electives RME 94(1), ICT 70(2) = 8
    assert akua.aggregate == 8
    assert akua.status == "draft"


def test_drafts_are_hidden_from_parents_until_published(campus, results, make_member, api):
    parent = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(
            student=results["a"], guardian_user_id=parent.pk, phone="+233244123456"
        )
    parent_client = api(parent, campus.tenant)
    assert parent_client.get("/api/v1/assessments/report-cards/").data == []

    published = results["client"].post(
        "/api/v1/assessments/results/publish/",
        {"arm": str(campus.jhs1.pk), "term": campus.term.pk},
        format="json",
    )
    assert published.data == {"published": 3}
    cards = parent_client.get("/api/v1/assessments/report-cards/").data
    assert [c["student_name"] for c in cards] == [results["a"].full_name]
    assert cards[0]["has_pdf"] is True
    pdf = parent_client.get(f"/api/v1/assessments/report-cards/{cards[0]['id']}/pdf/")
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert b"".join(pdf.streaming_content).startswith(b"%PDF")


def test_published_scores_are_locked_and_amendments_audited(campus, results, make_member, api):
    results["client"].post(
        "/api/v1/assessments/results/publish/",
        {"arm": str(campus.jhs1.pk), "term": campus.term.pk},
        format="json",
    )
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    locked = _enter(admin, campus, campus.jhs1, "ENG", {results["c"]: (30, 70)})
    assert locked.status_code == 400

    comps = _components(campus.tenant)
    body = {
        "student": str(results["c"].pk),
        "subject": campus.subjects["ENG"].pk,
        "term": campus.term.pk,
        "component": comps["EXAM"],
        "score": "60",
        "reason": "Exam script re-marked after appeal",
    }
    assert admin.post("/api/v1/assessments/scores/amend/", body, format="json").status_code == 403
    short = results["client"].post(
        "/api/v1/assessments/scores/amend/", {**body, "reason": "typo"}, format="json"
    )
    assert short.status_code == 400
    ok = results["client"].post("/api/v1/assessments/scores/amend/", body, format="json")
    assert ok.status_code == 200, ok.data
    with tenant_context(campus.tenant):
        event = AuditEvent.objects.get(action="assessments.score_amended")
        assert event.before == {"score": "30.00"}
        assert event.reason == "Exam script re-marked after appeal"
        card = ReportCard.objects.get(student=results["c"])
        eng = next(line for line in card.lines if line["code"] == "ENG")
        assert eng["total"] == "75.00"
        assert card.status == "published"
        assert not card.needs_regeneration  # PDF re-rendered


def test_only_class_teacher_or_head_writes_comments(campus, results, make_member, assign, api):
    with tenant_context(campus.tenant):
        card = ReportCard.objects.get(student=results["a"])
    url = f"/api/v1/assessments/report-cards/{card.pk}/"
    subject_teacher = make_member(campus.tenant, Role.TEACHER)
    assign(subject_teacher, campus.jhs1, campus.subjects["MTH"])
    class_teacher = make_member(campus.tenant, Role.FORM_TEACHER)
    assign(class_teacher, campus.jhs1, form=True)
    assert (
        api(subject_teacher, campus.tenant)
        .patch(url, {"form_teacher_comment": "Good"}, format="json")
        .status_code
        == 403
    )
    assert (
        api(class_teacher, campus.tenant)
        .patch(url, {"principal_comment": "Good"}, format="json")
        .status_code
        == 403
    )
    assert (
        api(class_teacher, campus.tenant)
        .patch(url, {"form_teacher_comment": "Hardworking and respectful."}, format="json")
        .status_code
        == 200
    )


def test_components_must_total_100(campus, make_member, make_student, api):
    admin = api(make_member(campus.tenant, Role.ADMIN), campus.tenant)
    s1 = make_student(campus.tenant, arm=campus.jhs1)
    _enter(admin, campus, campus.jhs1, "MTH", {s1: (20, 50)})
    with tenant_context(campus.tenant):
        AssessmentComponent.objects.filter(code="EXAM").update(max_score=60)
    principal = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    response = principal.post(
        "/api/v1/assessments/results/compute/",
        {"arm": str(campus.jhs1.pk), "term": campus.term.pk},
        format="json",
    )
    assert response.status_code == 400
