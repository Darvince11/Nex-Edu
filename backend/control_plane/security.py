"""What the System page shows about security and updates.

Sign-in activity comes from the platform audit log (every sign-in, failure,
password reset and authenticator change is already recorded there), matched
to schools through memberships. Vulnerabilities come from OSV, the open
advisory database, for the exact Python packages this server runs.
"""

from __future__ import annotations

import datetime as dt
import platform as python_platform
from collections import defaultdict
from importlib import metadata
from typing import Any

import django
from django.conf import settings
from django.core import checks
from django.db.models import Count, Max
from django.utils import timezone

from control_plane.models import Membership, PlatformAuditEvent, Tenant, User, VulnerabilityScan

REPEATED_FAILURES = 5  # failed sign-ins on one account within the window
MANY_ACCOUNTS_FROM_ONE_ADDRESS = 5  # different accounts tried from one IP
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"


def _schools_by_user(user_ids: set[str]) -> dict[str, list[dict[str, str]]]:
    schools: dict[str, list[dict[str, str]]] = defaultdict(list)
    for user_id, slug, name in (
        Membership.objects.filter(user_id__in=user_ids, is_active=True)
        .values_list("user_id", "tenant__slug", "tenant__name")
        .distinct()
    ):
        entry = {"slug": slug, "name": name}
        if entry not in schools[str(user_id)]:
            schools[str(user_id)].append(entry)
    return schools


def sign_in_activity(hours: int = 24) -> dict[str, Any]:
    """Failed sign-ins (by account and by address), resets and authenticator changes."""
    since = timezone.now() - dt.timedelta(hours=hours)
    events = PlatformAuditEvent.objects.filter(occurred_at__gte=since)
    failed = events.filter(action="auth.sign_in_failed")

    by_email: dict[str, dict[str, Any]] = {}
    for e in failed.values("data", "ip", "occurred_at"):
        email = (e["data"] or {}).get("email", "")
        row = by_email.setdefault(
            email, {"email": email, "attempts": 0, "addresses": set(), "last": None}
        )
        row["attempts"] += 1
        row["addresses"].add(e["ip"])
        row["last"] = max(filter(None, [row["last"], e["occurred_at"]]))
    users = {u.email: u for u in User.objects.filter(email__in=list(by_email))}
    schools = _schools_by_user({str(u.pk) for u in users.values()})
    accounts = sorted(
        (
            {
                "email": email,
                "attempts": row["attempts"],
                "addresses": len(row["addresses"]),
                "last_attempt": row["last"],
                "known_account": email in users,
                "schools": schools.get(str(users[email].pk), []) if email in users else [],
                "suspicious": row["attempts"] >= REPEATED_FAILURES,
            }
            for email, row in by_email.items()
        ),
        key=lambda r: (-r["attempts"], r["email"]),
    )
    addresses = [
        {
            "ip": row["ip"] or "unknown",
            "accounts": row["accounts"],
            "attempts": row["attempts"],
            "last": row["last"],
        }
        for row in failed.values("ip")
        .annotate(
            accounts=Count("data__email", distinct=True),
            attempts=Count("pk"),
            last=Max("occurred_at"),
        )
        .order_by("-attempts")
        if row["accounts"] >= MANY_ACCOUNTS_FROM_ONE_ADDRESS
    ]

    def people_events(actions: list[str]) -> list[dict[str, Any]]:
        rows = list(
            events.filter(action__in=actions)
            .order_by("-seq")
            .values("action", "actor_id", "target_id", "actor_email", "occurred_at", "ip")[:100]
        )
        ids = {str(r["actor_id"] or r["target_id"]) for r in rows}
        found = _schools_by_user(ids)
        emails = dict(
            User.objects.filter(pk__in=[i for i in ids if len(i) == 36]).values_list("pk", "email")
        )
        return [
            {
                "action": r["action"],
                "email": r["actor_email"] or emails.get(r["target_id"], ""),
                "occurred_at": r["occurred_at"],
                "ip": r["ip"],
                "schools": found.get(str(r["actor_id"] or r["target_id"]), []),
            }
            for r in rows
        ]

    return {
        "hours": hours,
        "failed_sign_ins": failed.count(),
        "successful_sign_ins": events.filter(action="auth.signed_in").count(),
        "accounts": accounts,
        "suspicious_addresses": addresses,
        "password_resets": people_events(
            ["auth.password_reset_requested", "auth.password_reset", "auth.password_changed"]
        ),
        "authenticator_changes": people_events(
            ["auth.mfa_added", "auth.mfa_removed", "auth.mfa_reset"]
        ),
    }


def system_status() -> dict[str, Any]:
    """Versions, which school databases need updating, and Django's own security checks."""
    from control_plane.migration_runner import tenant_schema_version

    current = tenant_schema_version()
    tenants = Tenant.objects.filter(status=Tenant.Status.ACTIVE).order_by("name")
    behind = [
        {"slug": t.slug, "name": t.name, "migrated_at": t.migrated_at}
        for t in tenants
        if t.schema_version != current
    ]
    problems = checks.run_checks(
        include_deployment_checks=not settings.DEBUG, tags=[checks.Tags.security]
    )
    return {
        "app_version": settings.APP_VERSION,
        "release": settings.APP_RELEASE,
        "python": python_platform.python_version(),
        "django": django.get_version(),
        "debug": settings.DEBUG,
        "schema_version": current,
        "schools": tenants.count(),
        "schools_behind": behind,
        "platform_mfa_required": settings.PLATFORM_MFA_REQUIRED,
        "school_mfa_roles": sorted(settings.MFA_REQUIRED_ROLES),
        "breached_password_check": settings.BREACHED_PASSWORD_CHECK_ENABLED,
        "security_checks": [
            {
                "id": c.id,
                "level": "error" if c.is_serious() else "warning",
                "message": c.msg,
                "hint": c.hint or "",
            }
            for c in problems
        ],
    }


def installed_packages() -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for dist in metadata.distributions():
        name = (dist.metadata["Name"] or "").strip()
        if name:
            seen[name.lower()] = dist.version
    return sorted(seen.items())


def scan_vulnerabilities() -> VulnerabilityScan:
    """Ask OSV which installed packages have published advisories. One request for
    all packages, then one per advisory found for its summary and fix version."""
    from integrations.http import client

    scan = VulnerabilityScan.objects.create(started_at=timezone.now())
    packages = installed_packages()
    try:
        with client() as http:
            response = http.post(
                OSV_BATCH,
                json={
                    "queries": [
                        {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
                        for name, version in packages
                    ]
                },
            )
            response.raise_for_status()
            findings = []
            for (name, version), result in zip(
                packages, response.json().get("results", []), strict=False
            ):
                for vuln in result.get("vulns") or []:
                    detail = http.get(OSV_VULN.format(vuln["id"]))
                    info = detail.json() if detail.status_code == 200 else {}
                    fixed = sorted(
                        {
                            event["fixed"]
                            for affected in info.get("affected", [])
                            for rng in affected.get("ranges", [])
                            for event in rng.get("events", [])
                            if "fixed" in event
                        }
                    )
                    findings.append(
                        {
                            "package": name,
                            "version": version,
                            "id": vuln["id"],
                            "aliases": info.get("aliases", [])[:5],
                            "summary": (info.get("summary") or info.get("details", ""))[:300],
                            "fixed_in": fixed[:3],
                            "url": f"https://osv.dev/vulnerability/{vuln['id']}",
                        }
                    )
        scan.findings = findings
    except Exception as exc:
        scan.error = f"Couldn't reach the advisory database: {type(exc).__name__}"[:500]
    scan.packages_checked = len(packages)
    scan.finished_at = timezone.now()
    scan.save()
    return scan
