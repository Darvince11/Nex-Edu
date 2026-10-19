from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from allauth.mfa.models import Authenticator
from django.conf import settings as dj_settings
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from rest_framework.test import APIClient

from control_plane.db import forget_tenant_connection, registered_tenant_aliases
from control_plane.models import Membership, Tenant, User
from control_plane.provisioning.service import provision_tenant
from control_plane.tenancy import tenant_context
from core.crypto import clear_key_cache


@pytest.fixture(autouse=True)
def _isolated_tenant_storage(settings: Any, tmp_path: Any) -> Iterator[None]:
    """Every test gets fresh school databases and a fresh secrets file."""
    from django.core.cache import cache

    settings.TENANT_SQLITE_DIR = tmp_path / "tenants"
    settings.TENANT_SECRETS_FILE = tmp_path / "secrets.json"
    settings.MEDIA_ROOT = tmp_path / "media"
    cache.clear()
    yield
    cache.clear()
    for alias in registered_tenant_aliases():
        forget_tenant_connection(alias)
    clear_key_cache()


@pytest.fixture
def _allow_tenant_databases(
    db: None, django_db_blocker: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Django's test case only allows aliases declared up front, but school
    databases are registered at runtime. Let tenant aliases connect; every other
    alias keeps Django's guard."""
    guarded = BaseDatabaseWrapper.ensure_connection
    real = django_db_blocker._real_ensure_connection

    def ensure_connection(self: BaseDatabaseWrapper, *args: Any, **kwargs: Any) -> None:
        if self.alias.startswith(dj_settings.TENANT_DB_ALIAS_PREFIX):
            return real(self, *args, **kwargs)
        return guarded(self, *args, **kwargs)

    monkeypatch.setattr(BaseDatabaseWrapper, "ensure_connection", ensure_connection)


@pytest.fixture
def make_tenant(_allow_tenant_databases: None) -> Callable[..., Tenant]:
    def _make(slug: str = "greenfield", **kwargs: Any) -> Tenant:
        return provision_tenant(slug=slug, name=kwargs.pop("name", slug.title()), **kwargs)

    return _make


@pytest.fixture
def tenant(make_tenant: Callable[..., Tenant]) -> Tenant:
    return make_tenant("greenfield")


@pytest.fixture
def other_tenant(make_tenant: Callable[..., Tenant]) -> Tenant:
    return make_tenant("royal-heights")


def enroll_mfa(user: User) -> None:
    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={"secret": "x"})


@pytest.fixture
def make_member(db: None) -> Callable[..., User]:
    counter = {"n": 0}

    def _make(tenant: Tenant, *roles: str, mfa: bool = True, email: str | None = None) -> User:
        counter["n"] += 1
        user = User.objects.create_user(email or f"user{counter['n']}@example.test", "x" * 16)
        for role in roles:
            Membership.objects.create(user=user, tenant=tenant, role=role)
        if mfa:
            enroll_mfa(user)
        return user

    return _make


@pytest.fixture
def api() -> Callable[..., APIClient]:
    def _client(user: User | None, tenant: Tenant | None) -> APIClient:
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        if tenant is not None:
            client.credentials(HTTP_X_TENANT=tenant.slug)
        return client

    return _client


@pytest.fixture
def make_student() -> Callable[..., Any]:
    from apps.students.models import Student
    from apps.students.services import create_student

    counter = {"n": 0}

    def _make(tenant: Tenant, **data: Any) -> Student:
        counter["n"] += 1
        defaults = {
            "admission_number": f"ADM{counter['n']:04d}",
            "first_name": "Ama",
            "last_name": f"Mensah{counter['n']}",
            "date_of_birth": dt.date(2014, 3, 1),
            "gender": "female",
        }
        with tenant_context(tenant):
            return create_student(request=None, data={**defaults, **data})

    return _make


@pytest.fixture
def campus(tenant: Tenant) -> SimpleNamespace:
    """A school mid-term: current year and term around today, JHS classes, subjects."""
    from apps.academics.models import AcademicSession, ClassArm, Subject, Term

    today = timezone.localdate()
    with tenant_context(tenant):
        session = AcademicSession.objects.create(
            name="2026/2027",
            starts_on=today - dt.timedelta(days=60),
            ends_on=today + dt.timedelta(days=300),
            is_current=True,
        )
        term = Term.objects.create(
            session=session,
            number=1,
            starts_on=today - dt.timedelta(days=30),
            ends_on=today + dt.timedelta(days=60),
            is_current=True,
            next_term_begins=today + dt.timedelta(days=80),
        )
        arms = {a.level.name: a for a in ClassArm.objects.select_related("level")}
        subjects = {s.code: s for s in Subject.objects.all()}
    return SimpleNamespace(
        tenant=tenant,
        session=session,
        term=term,
        today=today,
        jhs1=arms["JHS 1"],
        jhs2=arms["JHS 2"],
        basic4=arms["Basic 4"],
        subjects=subjects,
    )


@pytest.fixture
def assign(tenant: Tenant) -> Callable[..., Any]:
    from apps.academics.models import TeachingAssignment

    def _assign(user: User, arm: Any, subject: Any = None, *, form: bool = False) -> Any:
        with tenant_context(tenant):
            return TeachingAssignment.objects.create(
                teacher_user_id=user.pk, arm=arm, subject=subject, is_form_teacher=form
            )

    return _assign


@pytest.fixture
def mock_http() -> Iterator[Callable[[Callable[[httpx.Request], httpx.Response]], None]]:
    """Route all provider HTTP calls to a handler; records requests on .calls."""
    from integrations.http import use_transport

    stack: list[Any] = []

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        cm = use_transport(httpx.MockTransport(handler))
        cm.__enter__()
        stack.append(cm)

    yield install
    while stack:
        stack.pop().__exit__(None, None, None)
