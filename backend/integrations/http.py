"""One outbound HTTP client for every provider, with tight timeouts.

Tests install a mock transport with ``use_transport`` so no real network is used.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

_transport: httpx.BaseTransport | None = None

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def client(**kwargs: object) -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT,
        transport=_transport,
        headers={"User-Agent": "nexedu-api"},
        follow_redirects=False,
        **kwargs,  # type: ignore[arg-type]
    )


@contextmanager
def use_transport(transport: httpx.BaseTransport) -> Iterator[None]:
    global _transport
    previous, _transport = _transport, transport
    try:
        yield
    finally:
        _transport = previous
