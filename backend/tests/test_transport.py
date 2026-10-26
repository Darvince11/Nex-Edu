"""School transport: routes and stops, riders, the driver's list, parents' notes."""

from __future__ import annotations

import pytest

from apps.communication.models import Notification
from apps.students.models import StudentGuardian
from control_plane.models import Role
from control_plane.modules import set_active
from control_plane.tenancy import tenant_context

pytestmark = pytest.mark.django_db

URL = "/api/v1/transport/"


@pytest.fixture
def bus(campus, make_member, make_student, api):
    set_active(tenant=campus.tenant, code="transport", active=True, request=None)
    head = api(make_member(campus.tenant, Role.PRINCIPAL), campus.tenant)
    driver_user = make_member(campus.tenant, Role.DRIVER)
    vehicle = head.post(
        f"{URL}vehicles/",
        {
            "name": "Bus 1",
            "registration": "GR 1234-23",
            "seats": 2,
            "driver_user_id": str(driver_user.pk),
        },
        format="json",
    )
    assert vehicle.status_code == 201, vehicle.content
    route = head.post(
        f"{URL}routes/",
        {
            "name": "Kasoa route",
            "vehicle": vehicle.json()["id"],
            "stops": [
                {"name": "Kasoa junction", "pickup_at": "06:30", "drop_at": "15:45"},
                {"name": "Old Barrier", "pickup_at": "06:45", "drop_at": "15:30"},
            ],
        },
        format="json",
    )
    assert route.status_code == 201, route.content
    child = make_student(campus.tenant, arm=campus.jhs1, first_name="Kojo")
    parent_user = make_member(campus.tenant, Role.PARENT, mfa=False)
    with tenant_context(campus.tenant):
        StudentGuardian.objects.create(student=child, guardian_user_id=parent_user.pk)
    return {
        "head": head,
        "driver": api(driver_user, campus.tenant),
        "other_driver": api(make_member(campus.tenant, Role.DRIVER), campus.tenant),
        "parent": api(parent_user, campus.tenant),
        "parent_user": parent_user,
        "route": route.json(),
        "child": child,
    }


def test_riders_fill_the_seats_and_move_between_routes(campus, bus, make_student):
    route = bus["route"]
    stop = route["stops"][0]["id"]
    add = f"{URL}routes/{route['id']}/add_rider/"
    assert bus["head"].post(add, {"student": str(bus["child"].pk), "stop": stop}).status_code == 201
    second = make_student(campus.tenant, arm=campus.jhs1)
    assert bus["head"].post(add, {"student": str(second.pk), "stop": stop}).status_code == 201
    third = make_student(campus.tenant, arm=campus.jhs2)
    full = bus["head"].post(add, {"student": str(third.pk), "stop": stop})
    assert full.status_code == 400 and "full" in str(full.json())
    riders = bus["head"].get(f"{URL}riders/").json()
    assert {r["stop"] for r in riders} == {"Kasoa junction"}
    # A stop that pupils use can't be removed.
    keep_one = bus["head"].patch(
        f"{URL}routes/{route['id']}/",
        {"stops": [{"id": route["stops"][1]["id"], "name": "Old Barrier"}]},
        format="json",
    )
    assert keep_one.status_code == 400


def test_the_driver_keeps_the_list_and_parents_hear(campus, bus):
    route = bus["route"]
    bus["head"].post(
        f"{URL}routes/{route['id']}/add_rider/",
        {"student": str(bus["child"].pk), "stop": route["stops"][1]["id"]},
    )
    assert [r["name"] for r in bus["driver"].get(f"{URL}routes/").json()] == ["Kasoa route"]
    assert bus["other_driver"].get(f"{URL}routes/").json() == []
    roll = bus["driver"].get(f"{URL}routes/{route['id']}/roll/", {"direction": "morning"}).json()
    assert roll["riders"][0]["stop"] == "Old Barrier" and roll["riders"][0]["status"] == ""
    mark = {"student": str(bus["child"].pk), "direction": "morning", "status": "boarded"}
    assert bus["other_driver"].post(f"{URL}routes/{route['id']}/mark/", mark).status_code == 404
    assert bus["driver"].post(f"{URL}routes/{route['id']}/mark/", mark).status_code == 200
    bus["driver"].post(f"{URL}routes/{route['id']}/mark/", mark)  # again: no second note
    bus["driver"].post(
        f"{URL}routes/{route['id']}/mark/",
        {"student": str(bus["child"].pk), "direction": "afternoon", "status": "dropped"},
    )
    with tenant_context(campus.tenant):
        notes = list(
            Notification.objects.filter(recipient_user_id=bus["parent_user"].pk, kind="transport")
            .order_by("created_at")
            .values_list("body", flat=True)
        )
    assert len(notes) == 2
    assert "got on the school bus" in notes[0] and "dropped off at Old Barrier" in notes[1]

    mine = bus["parent"].get(f"{URL}mine/").json()
    assert mine[0]["route"] == "Kasoa route" and mine[0]["stop"] == "Old Barrier"
    assert mine[0]["today"] == {"morning": "Got on", "afternoon": "Dropped off"}
    assert bus["parent"].get(f"{URL}routes/").status_code == 403


def test_only_drivers_drive(campus, bus, make_member):
    teacher = make_member(campus.tenant, Role.TEACHER)
    refused = bus["head"].post(
        f"{URL}vehicles/", {"name": "Bus 2", "driver_user_id": str(teacher.pk)}, format="json"
    )
    assert refused.status_code == 400
    assert (
        bus["driver"].post(f"{URL}vehicles/", {"name": "Bus 3"}, format="json").status_code == 403
    )
