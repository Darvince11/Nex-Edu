"""Second factor: an authenticator app (TOTP). Recovery codes are a backup only."""

from __future__ import annotations

import pytest
from allauth.mfa.models import Authenticator

from control_plane.models import PlatformRole, PlatformStaff, Role


def add_factor(user, kind: str) -> None:
    Authenticator.objects.create(user=user, type=kind, data={"secret": "x"})


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("factors", "allowed"),
    [
        ([], False),
        ([Authenticator.Type.RECOVERY_CODES], False),
        ([Authenticator.Type.TOTP], True),
        ([Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES], True),
    ],
    ids=["none", "recovery codes only", "app", "app and codes"],
)
def test_only_an_authenticator_app_counts_where_required(
    tenant, make_member, api, settings, factors, allowed
):
    settings.MFA_REQUIRED_ROLES = frozenset({Role.TEACHER})
    teacher = make_member(tenant, Role.TEACHER, mfa=False)
    for kind in factors:
        add_factor(teacher, kind)
    response = api(teacher, tenant).get("/api/v1/students/")
    if allowed:
        assert response.status_code == 200, response.content
    else:
        assert response.status_code == 403
        assert response.data["code"] == "mfa_enrollment_required"
    assert api(teacher, None).get("/api/v1/me/").data["mfa_enrolled"] is allowed


@pytest.mark.django_db
def test_platform_staff_follow_the_same_rule_when_required(tenant, make_member, api, settings):
    settings.PLATFORM_MFA_REQUIRED = True
    ops = make_member(tenant, mfa=False)
    PlatformStaff.objects.create(user=ops, role=PlatformRole.SUPPORT)
    add_factor(ops, Authenticator.Type.RECOVERY_CODES)
    assert api(ops, None).get("/api/v1/platform/tenants/").status_code == 403
    add_factor(ops, Authenticator.Type.TOTP)
    assert api(ops, None).get("/api/v1/platform/tenants/").status_code == 200


def test_codes_one_step_either_side_are_accepted_but_no_further():
    """MFA_TOTP_TOLERANCE = 1: a code typed as it rolls over still works."""
    from unittest import mock

    from allauth.mfa.totp.internal import auth as totp

    secret = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
    now = 1_800_000_015
    step = now // 30
    with mock.patch.object(totp.time, "time", return_value=now):
        for offset, accepted in ((-1, True), (0, True), (1, True), (-2, False), (2, False)):
            code = totp.format_hotp_value(totp.hotp_value(secret, step + offset))
            assert totp.validate_totp_code(secret, code) is accepted, offset
