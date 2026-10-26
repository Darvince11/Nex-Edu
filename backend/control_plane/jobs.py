"""A record of every scheduled background job run, for the console's jobs view.

Only the jobs in ``CELERY_BEAT_SCHEDULE`` are recorded (one-off tasks such as
sending a message are too many to keep). Recording never breaks the job itself.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from celery.signals import task_postrun, task_prerun
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

KEEP_DAYS = 30
_running: dict[str, int] = {}


def scheduled() -> dict[str, dict[str, Any]]:
    """Task name -> {"key", "every_seconds"} for every job on the schedule."""
    jobs = {}
    for key, entry in settings.CELERY_BEAT_SCHEDULE.items():
        every = entry["schedule"]
        jobs[entry["task"]] = {
            "key": key,
            "every_seconds": int(every.total_seconds())
            if isinstance(every, dt.timedelta)
            else None,
        }
    return jobs


@task_prerun.connect
def _started(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    if task is None or task.name not in scheduled() or task_id is None:
        return
    from control_plane.models import JobRun

    try:
        _running[task_id] = JobRun.objects.create(name=task.name, started_at=timezone.now()).pk
    except Exception:
        logger.exception("Could not record the start of %s", task.name)


@task_postrun.connect
def _finished(
    task_id: str | None = None, retval: Any = None, state: str | None = None, **_: Any
) -> None:
    pk = _running.pop(task_id or "", None)
    if pk is None:
        return
    from control_plane.models import JobRun

    ok = state == "SUCCESS"
    try:
        JobRun.objects.filter(pk=pk).update(
            finished_at=timezone.now(),
            succeeded=ok,
            result=str(retval)[:300] if ok else "",
            error="" if ok else str(retval)[:2000],
        )
        JobRun.objects.filter(started_at__lt=timezone.now() - dt.timedelta(days=KEEP_DAYS)).delete()
    except Exception:
        logger.exception("Could not record the end of job %s", pk)


def overview() -> list[dict[str, Any]]:
    """Each scheduled job: how often, the last run and whether it is late or failing."""
    from control_plane.models import JobRun

    now = timezone.now()
    rows = []
    for name, job in sorted(scheduled().items(), key=lambda kv: kv[1]["key"]):
        runs = list(JobRun.objects.filter(name=name)[:20])
        last = runs[0] if runs else None
        every = job["every_seconds"]
        late = bool(
            every and (last is None or (now - last.started_at).total_seconds() > every * 2 + 300)
        )
        rows.append(
            {
                "name": name,
                "key": job["key"],
                "every_seconds": every,
                "last_started_at": last.started_at if last else None,
                "last_finished_at": last.finished_at if last else None,
                "last_succeeded": last.succeeded if last else None,
                "last_result": last.result if last else "",
                "last_error": last.error if last else "",
                "failures_recent": sum(1 for r in runs if r.succeeded is False),
                "late": late,
            }
        )
    return rows
