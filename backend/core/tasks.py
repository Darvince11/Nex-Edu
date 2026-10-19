"""Celery base task that runs inside a school's tenant context.

The school must be passed explicitly. Background work never inherits a school
implicitly, so a task can't run against the wrong database.
"""

from __future__ import annotations

from typing import Any

from celery import Task

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
