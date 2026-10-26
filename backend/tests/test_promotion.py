"""End of year: classes move up a level, the top class graduates, with exceptions."""

from __future__ import annotations

import pytest

from apps.academics.models import ClassArm, ClassLevel
from apps.students.models import PromotionRun, Student
from control_plane.models import Role
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db
URL = "/api/v1/promotion/"


def test_plan_moves_each_class_up_and_graduates_the_top(campus, make_member, make_student, api):
    make_student(campus.tenant, arm=campus.jhs1)
    with tenant_context(campus.tenant):
        jhs3 = ClassArm.objects.get(level__name="JHS 3", name="A")
    make_student(campus.tenant, arm=jhs3)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    classes = {c["label"]: c for c in head.get(URL).data["classes"]}
    assert classes["JHS 1 A"]["to"] == "JHS 2 A" and classes["JHS 1 A"]["default"] == "promote"
    assert classes["JHS 3 A"]["to"] is None and classes["JHS 3 A"]["default"] == "graduate"
    assert api(make_member(campus.tenant, Role.TEACHER), campus.tenant).get(URL).status_code == 403


def test_apply_moves_pupils_with_exceptions_and_keeps_a_record(
    campus, make_member, make_student, api
):
    staying = make_student(campus.tenant, arm=campus.jhs1, first_name="Staying")
    moving = make_student(campus.tenant, arm=campus.jhs1, first_name="Moving")
    leaving = make_student(campus.tenant, arm=campus.jhs2, first_name="Leaving")
    with tenant_context(campus.tenant):
        jhs3 = ClassArm.objects.get(level__name="JHS 3", name="A")
    graduating = make_student(campus.tenant, arm=jhs3, first_name="Graduating")
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)

    done = head.post(
        URL,
        {"overrides": {str(staying.pk): "repeat", str(leaving.pk): "leave"}},
        format="json",
    )
    assert done.status_code == 201, done.content
    assert done.data["summary"] == {"promoted": 1, "repeated": 1, "graduated": 1, "left": 1}
    with tenant_context(campus.tenant):
        assert Student.objects.get(pk=staying.pk).arm_id == campus.jhs1.pk
        assert Student.objects.get(pk=moving.pk).arm_id == campus.jhs2.pk
        assert Student.objects.get(pk=leaving.pk).status == "withdrawn"
        assert Student.objects.get(pk=graduating.pk).status == "graduated"
        assert PromotionRun.objects.count() == 1

    # Running again in the same year would move pupils twice: it needs confirming.
    again = head.post(URL, {}, format="json")
    assert again.status_code == 409
    assert head.post(URL, {"confirm": True}, format="json").status_code == 201


def test_a_missing_next_arm_is_created(campus, make_member, make_student, api):
    with tenant_context(campus.tenant):
        b_arm = ClassArm.objects.create(level=ClassLevel.objects.get(name="JHS 1"), name="B")
    pupil = make_student(campus.tenant, arm=b_arm)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    assert head.post(URL, {}, format="json").status_code == 201
    with tenant_context(campus.tenant):
        moved = Student.objects.select_related("arm__level").get(pk=pupil.pk)
        assert str(moved.arm) == "JHS 2 B"


def test_unknown_actions_are_refused(campus, make_member, make_student, api):
    pupil = make_student(campus.tenant, arm=campus.jhs1)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    bad = head.post(URL, {"overrides": {str(pupil.pk): "expel"}}, format="json")
    assert bad.status_code == 400
