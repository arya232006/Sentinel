"""Shared-secret gate over the API surface.

Enabled by setting SENTINEL_API_TOKEN; unset leaves the API open, which is what
the test suite and a loopback dev server want. See config.api_token for why a
public deployment cannot skip it.

The token is accepted from `X-Sentinel-Token`, from `Authorization: Bearer`, or
from a `?token=` query parameter. The query form exists for exactly one caller:
the console streams /runs/{id}/events through EventSource, which cannot set
request headers. It is the weaker channel - query strings are recorded in proxy
and access logs where headers are not - so every other call should use a header.
"""

from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.responses import JSONResponse

from sentinel import config

# Reachable without a token. A load balancer health check has no way to hold a
# secret, so /healthz answers unauthenticated - and reports nothing but
# liveness. /health, which discloses model ids, budget caps and whether an API
# key is loaded, stays behind the gate.
PUBLIC_PATHS = frozenset({"/healthz"})


def presented_token(request: Request) -> str:
    """The token this request offers, by whichever of the three channels."""
    header = request.headers.get("x-sentinel-token", "")
    if header.strip():
        return header.strip()

    authorization = request.headers.get("authorization", "")
    if authorization[:7].lower() == "bearer ":
        return authorization[7:].strip()

    return (request.query_params.get("token") or "").strip()


async def token_gate(request: Request, call_next):
    """Reject any request that does not present the configured token."""
    expected = config.api_token()
    if not expected:
        return await call_next(request)

    # A CORS preflight is sent by the browser before - and without - the
    # authenticated request behind it, and carries no custom headers by
    # definition. Rejecting it means the real request is never sent at all, so
    # the failure surfaces as an opaque CORS error rather than a 401.
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    # Compared as bytes: compare_digest rejects str operands outside ASCII with
    # a TypeError, and the presented value is attacker-controlled.
    if not hmac.compare_digest(
        presented_token(request).encode("utf-8"), expected.encode("utf-8")
    ):
        return JSONResponse(
            {"detail": "invalid or missing API token"},
            status_code=401,
        )

    return await call_next(request)
