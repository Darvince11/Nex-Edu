"""Catch failures before schools notice them: the console's Problems list.

Sources: errors logged anywhere (server errors, failed background jobs),
slow requests, errors reported by people's browsers, and scheduled health
checks. Repeats of one failure are grouped by a fingerprint and counted.
Everything stored is scrubbed of emails, phone numbers, long numbers and
secrets first, so the list never becomes a copy of school data.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import traceback
from typing import Any

from django.conf import settings
from django.db import connections
from django.utils import timezone

logger = logging.getLogger(__name__)

SLOW_REQUEST_SECONDS = 3.0
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+?233|0)[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\w)")
_LONG_NUMBER = re.compile(r"\b\d{7,}\b")
_SECRET = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|sessionid|csrftoken)"
    r"(['\"]?\s*[:=]\s*)(['\"]?)[^\s'\",}]+"
)
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_local = threading.local()


def scrub(text: str, limit: int = 8000) -> str:
    """Remove personal details and secrets from a message or traceback."""
    text = _SECRET.sub(r"\1\2\3[removed]", text)
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    text = _LONG_NUMBER.sub("[number]", text)
    return text[:limit]


def _normalise_path(path: str) -> str:
    """/api/v1/students/0f4c…/ and /api/v1/students/1a2b…/ are the same page."""
    path = _UUID.sub(":id", path.split("?")[0])
    return re.sub(r"/\d+(?=/|$)", "/:n", path)[:300]


def _our_frame(tb: Any) -> str:
    """The deepest frame in Nex Edu's own code (not a library): where to start looking."""
    base = str(settings.BASE_DIR)
    where = ""
    for frame in traceback.extract_tb(tb):
        if frame.filename.startswith(base) and ".venv" not in frame.filename:
            relative = frame.filename[len(base) :].replace("\\", "/").lstrip("/")
            where = f"{relative}:{frame.lineno} in {frame.name}"
    return where


def _current_school() -> str:
    from control_plane.tenancy import get_current_tenant

    tenant = get_current_tenant()
    return tenant.slug if tenant else ""


def capture(
    *,
    kind: str,
    title: str,
    location: str = "",
    detail: str = "",
    path: str = "",
    school: str = "",
    severity: str | None = None,
    fingerprint: str | None = None,
) -> Any:
    """Record one occurrence. Never raises: a broken error tracker must not break the app."""
    from control_plane.models import Problem

    if getattr(_local, "busy", False):
        return None  # an error while recording an error: don't loop
    _local.busy = True
    try:
        severity = severity or (
            Problem.Severity.WARNING
            if kind in (Problem.Kind.SLOW, Problem.Kind.BROWSER)
            else Problem.Severity.CRITICAL
        )
        title = scrub(title, 300)
        key = fingerprint or hashlib.sha256(f"{kind}|{location}|{title}".encode()).hexdigest()
        now = timezone.now()
        problem = Problem.objects.using("default").filter(fingerprint=key).first()
        if problem is None:
            problem = Problem.objects.using("default").create(
                fingerprint=key,
                kind=kind,
                severity=severity,
                title=title,
                location=location[:300],
                detail=scrub(detail),
                last_path=_normalise_path(path),
                schools=[school] if school else [],
                first_seen=now,
                last_seen=now,
            )
            _notify(problem, reopened=False)
            return problem
        reopened = problem.status == Problem.Status.FIXED
        problem.count += 1
        problem.last_seen = now
        problem.detail = scrub(detail) or problem.detail
        problem.last_path = _normalise_path(path) or problem.last_path
        if school and school not in problem.schools:
            problem.schools = [*problem.schools, school][-50:]
        if reopened:
            problem.status = Problem.Status.NEW
        problem.save(using="default")
        if reopened:
            _notify(problem, reopened=True)
        return problem
    except Exception:  # pragma: no cover - last resort, keep the app running
        logging.getLogger("nexedu.problems.internal").warning(
            "Could not record a problem", exc_info=True
        )
        return None
    finally:
        _local.busy = False


def _notify(problem: Any, *, reopened: bool) -> None:
    """Email active super admins about a new (or returning) critical problem."""
    if problem.severity != "critical":
        return
    from django.core.mail import send_mail

    from control_plane.models import PlatformRole, PlatformStaff

    recipients = list(
        PlatformStaff.objects.using("default")
        .filter(is_active=True, role=PlatformRole.SUPER_ADMIN)
        .values_list("user__email", flat=True)
    )
    if not recipients:
        return
    subject = f"[Nex Edu] {'Back again' if reopened else 'New problem'}: {problem.title[:120]}"
    where = problem.location or problem.last_path or "unknown place"
    body = (
        f"{problem.get_kind_display()} · {where}\n\n"
        f"{problem.title}\n\nSee it in the console: {settings.FRONTEND_URL}/platform/system\n"
    )

    def send() -> None:
        try:
            send_mail(subject, body, None, recipients, fail_silently=True)
        finally:
            connections.close_all()

    if getattr(settings, "PROBLEM_EMAILS_INLINE", False):
        send_mail(subject, body, None, recipients, fail_silently=True)
    else:
        threading.Thread(target=send, daemon=True).start()


class ProblemLogHandler(logging.Handler):
    """Turns ERROR log records (with or without an exception) into problems.

    Django logs every 500 on ``django.request``; Celery logs failed tasks; our
    own code logs with ``logger.exception``. All of them arrive here.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("nexedu.problems"):
            return
        from control_plane.models import Problem

        request = getattr(record, "request", None)
        path = getattr(request, "path", "") or ""
        is_job = record.name.startswith(("celery", "control_plane.tasks")) or "task" in record.name
        if record.exc_info and record.exc_info[1] is not None:
            exc_type, exc, tb = record.exc_info
            title = f"{exc_type.__name__ if exc_type else 'Error'}: {exc}"
            location = _our_frame(tb) or record.name
            detail = "".join(traceback.format_exception(exc_type, exc, tb))
        else:
            title = record.getMessage()
            location = f"{record.name} ({record.pathname.rsplit('/', 1)[-1]}:{record.lineno})"
            detail = title
        capture(
            kind=Problem.Kind.JOB if is_job else Problem.Kind.SERVER,
            title=title,
            location=location,
            detail=detail,
            path=path,
            school=_current_school(),
        )


class SlowRequestMiddleware:
    """Records pages that keep people waiting, grouped by page (not by pupil or id)."""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        started = time.monotonic()
        response = self.get_response(request)
        took = time.monotonic() - started
        if took >= SLOW_REQUEST_SECONDS and request.path.startswith("/api/"):
            from control_plane.models import Problem

            page = _normalise_path(request.path)
            capture(
                kind=Problem.Kind.SLOW,
                title=f"{request.method} {page} took {took:.1f} s",
                location=page,
                detail=f"{request.method} {page}: {took:.1f} s (limit {SLOW_REQUEST_SECONDS:.0f})",
                path=page,
                school=getattr(getattr(request, "tenant", None), "slug", ""),
                fingerprint=hashlib.sha256(f"slow|{request.method}|{page}".encode()).hexdigest(),
            )
        return response


def report_browser_error(*, message: str, source: str, stack: str, page: str, school: str) -> Any:
    from control_plane.models import Problem

    page = _normalise_path(page)
    message = message.strip()[:300] or "Unknown error"
    return capture(
        kind=Problem.Kind.BROWSER,
        title=message,
        location=(source or page)[:300],
        detail=stack[:6000],
        path=page,
        school=school,
        fingerprint=hashlib.sha256(f"browser|{message}|{source}".encode()).hexdigest(),
    )


# --- Health checks -----------------------------------------------------------------------


def run_health_checks() -> list[dict[str, Any]]:
    """Each school's database answers and is up to date; school figures are fresh.

    A failing check opens (or re-counts) a problem; a passing check marks its
    earlier problem fixed, so the list shows only what's wrong now.
    """
    from control_plane.migration_runner import tenant_schema_version
    from control_plane.models import Problem, Tenant, TenantUsage
    from control_plane.tenancy import tenant_context

    results = []
    current = tenant_schema_version()

    def outcome(key: str, ok: bool, title: str, detail: str = "", school: str = "") -> None:
        fingerprint = hashlib.sha256(f"health|{key}".encode()).hexdigest()
        results.append({"check": key, "ok": ok, "title": title, "school": school})
        if ok:
            Problem.objects.filter(
                fingerprint=fingerprint,
                status__in=[Problem.Status.NEW, Problem.Status.INVESTIGATING],
            ).update(status=Problem.Status.FIXED, updated_by_email="health check")
        else:
            capture(
                kind=Problem.Kind.HEALTH,
                title=title,
                location=key,
                detail=detail,
                school=school,
                fingerprint=fingerprint,
            )

    for tenant in Tenant.objects.filter(status=Tenant.Status.ACTIVE):
        try:
            with tenant_context(tenant):
                from django.db import connection

                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            outcome(
                f"db:{tenant.slug}", True, f"{tenant.name}: database answers", school=tenant.slug
            )
        except Exception as exc:
            outcome(
                f"db:{tenant.slug}",
                False,
                f"{tenant.name}: database not answering",
                detail=str(exc),
                school=tenant.slug,
            )
        up_to_date = tenant.schema_version == current
        outcome(
            f"schema:{tenant.slug}",
            up_to_date,
            f"{tenant.name}: database {'up to date' if up_to_date else 'needs updating'}",
            detail="" if up_to_date else "Run manage.py migrate_tenants to bring it up to date.",
            school=tenant.slug,
        )
    newest = (
        TenantUsage.objects.order_by("-collected_at").values_list("collected_at", flat=True).first()
    )
    fresh = newest is None or newest >= timezone.now() - timezone.timedelta(hours=3)
    outcome(
        "usage-fresh",
        fresh,
        "School figures are being counted" if fresh else "School figures stopped updating",
        detail=""
        if fresh
        else "The hourly control_plane.collect_usage job hasn't run for 3 hours.",
    )
    return results
