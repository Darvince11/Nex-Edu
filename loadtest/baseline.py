"""A quick local load baseline (no k6 needed): the same two scenarios as
results-and-fees.js, with a fixed number of parents clicking at once.

    backend/.venv/Scripts/python loadtest/baseline.py --base http://127.0.0.1:8000 \
        --email parent@greenfield.test --password ... --users 25 --seconds 60

Numbers from a developer laptop with SQLite are a floor to compare runs, not a
prediction for production; the real test is k6 against staging.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

PATHS = {
    "results_day": ["/api/v1/assessments/report-cards/", "/api/v1/communication/notifications/unread_count/"],
    "fee_deadline": ["/api/v1/finance/invoices/", "/api/v1/me/"],
}


async def user(client: httpx.AsyncClient, paths: list[str], stop: float, log: list[tuple[float, int]]) -> None:
    while time.monotonic() < stop:
        for path in paths:
            started = time.monotonic()
            try:
                status = (await client.get(path)).status_code
            except httpx.HTTPError:
                status = 0
            log.append((time.monotonic() - started, status))


def report(name: str, log: list[tuple[float, int]], seconds: float) -> dict[str, float]:
    times = sorted(t * 1000 for t, _ in log)
    errors = sum(1 for _, s in log if s == 0 or s >= 400)
    q = statistics.quantiles(times, n=100) if len(times) > 1 else [times[0]] * 99
    return {
        "scenario": name,
        "requests": len(log),
        "per_second": round(len(log) / seconds, 1),
        "p50_ms": round(q[49]),
        "p95_ms": round(q[94]),
        "p99_ms": round(q[98]),
        "error_rate": round(errors / len(log), 4) if log else 1.0,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--school", default="greenfield")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--users", type=int, default=25)
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=30) as anon:
        login = await anon.post(
            "/_allauth/app/v1/auth/login", json={"email": args.email, "password": args.password}
        )
        login.raise_for_status()
        token = login.json()["meta"]["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Tenant": args.school}
    limits = httpx.Limits(max_connections=args.users * 2)
    for name, paths in PATHS.items():
        log: list[tuple[float, int]] = []
        async with httpx.AsyncClient(base_url=args.base, headers=headers, timeout=30, limits=limits) as c:
            stop = time.monotonic() + args.seconds
            await asyncio.gather(*(user(c, paths, stop, log) for _ in range(args.users)))
        print(report(name, log, args.seconds))


if __name__ == "__main__":
    asyncio.run(main())
