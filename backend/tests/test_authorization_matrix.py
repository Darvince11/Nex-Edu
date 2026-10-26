"""Generated authorization matrix: every tenant endpoint, HTTP method and role.

Expectations come from ``core.rbac.ROLE_PERMISSIONS`` and each view's
``required_permissions``, so this can't drift from the code. Two properties are
checked for every combination:

1. A role whose permissions don't include what the endpoint needs gets 403.
2. A user who holds *every* role, but in another school, gets 403 everywhere.

Whether permitted roles see the *right records* (own classes, own children) is
covered by the scoping tests in ``test_authorization.py`` and each module's tests.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
from django.urls import get_resolver

from control_plane.models import Membership, Role
from core.permissions import required_permission_for
from core.rbac import ROLE_PERMISSIONS
from tests.test_authorization import _iter_views

METHODS = ("get", "post", "put", "patch", "delete")
_PATH_PARAM = re.compile(r"<(?:(?P<conv>\w+):)?(?P<name>\w+)>")  # path("<uuid:pk>/")
_REGEX_PARAM = re.compile(r"\(\?P<\w+>[^)]*\)")  # router: (?P<pk>[^/.]+)


def _concrete(route: str) -> str:
    """Fill URL parameters with placeholder values: a random UUID, so a
    permitted request finds nothing, but a refused one is refused first."""
    route = route.replace("^", "").replace("$", "")
    route = _REGEX_PARAM.sub(lambda m: str(uuid.uuid4()), route)
    return "/" + _PATH_PARAM.sub(lambda m: str(uuid.uuid4()), route)


def _tenant_endpoints() -> list[tuple[str, str, Any]]:
    """(url, method, needed permission) for every tenant-scoped API action."""
    found = []
    for route, callback in _iter_views(get_resolver()):
        view = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
        if not route.startswith("api/v1/") or view is None:
            continue
        if getattr(view, "public_endpoint", False) or getattr(view, "tenant_scoped", True) is False:
            continue
        actions = getattr(callback, "actions", None)
        if actions:
            pairs = [(m, a) for m, a in actions.items()]
        else:
            pairs = [(m, None) for m in METHODS if hasattr(view, m)]
        for method, action in pairs:
            probe = type(
                "Probe", (), {"action": action, "required_permissions": view.required_permissions}
            )
            needed = required_permission_for(probe, method.upper())
            options = (needed,) if isinstance(needed, str) else tuple(needed or ())
            found.append((_concrete(route), method, options))
    return found


ENDPOINTS = _tenant_endpoints()


def test_the_matrix_covers_the_api():
    assert len(ENDPOINTS) > 50
    assert all(options for _, _, options in ENDPOINTS), "an endpoint declares no permission"


@pytest.mark.django_db
def test_roles_without_the_permission_are_refused_everywhere(tenant, make_member, api, settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    failures = []
    for role in Role.values:
        user = make_member(tenant, role)
        client = api(user, tenant)
        granted = ROLE_PERMISSIONS[role]
        for url, method, options in ENDPOINTS:
            if any(p in granted for p in options):
                continue
            response = getattr(client, method)(url, {}, format="json")
            if response.status_code != 403:
                failures.append(f"{role} {method.upper()} {url} -> {response.status_code}")
    assert not failures, "\n".join(failures)


@pytest.mark.django_db
def test_members_of_another_school_are_refused_everywhere(
    tenant, other_tenant, make_member, api, settings
):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}
    outsider = make_member(other_tenant, *Role.values)
    assert Membership.objects.filter(user=outsider, tenant=tenant).count() == 0
    client = api(outsider, tenant)
    failures = [
        f"{method.upper()} {url} -> {status}"
        for url, method, _ in ENDPOINTS
        if (status := getattr(client, method)(url, {}, format="json").status_code) != 403
    ]
    assert not failures, "\n".join(failures)
