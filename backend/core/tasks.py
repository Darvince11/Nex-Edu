"""Celery base task that runs inside a school's tenant context.

The school must be passed explicitly. Background work never inherits a school
implicitly, so a task can't run against the wrong database.
"""

from __future__ import annotations

import threading
from typing import Any

from celery import Task
from django.conf import settings
from django.db import connections, transaction

from control_plane.tenancy import require_tenant, tenant_context


class TenantTask(Task):  # type: ignore[misc]
    abstract = True
    # Celery checks call arguments against the task function's signature when
    # queuing. ``tenant_slug`` is consumed here, not by the function, so that
    # check would reject every call. __call__ below enforces it instead.
    typing = False

    def __call__(self, *args: Any, tenant_slug: str | None = None, **kwargs: Any) -> Any:
        from control_plane.models import Tenant

        if not tenant_slug:
            raise ValueError(f"{self.name} requires tenant_slug")
        tenant = Tenant.objects.get(slug=tenant_slug, status=Tenant.Status.ACTIVE)
        with tenant_context(tenant):
            return super().__call__(*args, **kwargs)


def enqueue_for_current_tenant(task: Task, *args: Any, **kwargs: Any) -> Any:
    """Queue ``task`` for the school selected in the current context."""
    return task.apply_async(args=args, kwargs={**kwargs, "tenant_slug": require_tenant().slug})


def enqueue_after_commit(task: Task, *args: Any) -> None:
    """Queue ``task`` once the current transaction commits, so it never sees
    half-written data and the request returns straight away.

    Where no worker runs (local dev, ``TASKS_IN_THREADS``), the eager task runs on
    a background thread instead of inside the request. Threads start with an empty
    context, so no school selection leaks into the task.
    """

    def send() -> None:
        if getattr(settings, "TASKS_IN_THREADS", False):
            threading.Thread(target=_run_inline, args=(task, args), daemon=True).start()
        else:
            task.apply_async(args=args)

    transaction.on_commit(send)


def _run_inline(task: Task, args: tuple[Any, ...]) -> None:
    try:
        task.apply(args=args)
    finally:
        connections.close_all()
