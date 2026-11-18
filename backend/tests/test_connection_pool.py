"""Regression tests for the connection-pool stall (2.8.3)."""

import asyncio

import httpx
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.middleware.concurrency import ConcurrencyLimitMiddleware
from app.services.webhooks import dispatch_event


def test_dispatch_event_leaves_request_session_alone(db):
    # As a background task, dispatch_event runs after get_db() closed the
    # request session. Querying it again checked out a connection that was
    # never returned; it must use its own session instead.
    db.close()
    dispatch_event(db, "resource.shared", {"actor_name": "A", "title": "Drill"}, [], 1)
    assert not db.in_transaction()


def test_concurrency_limit_caps_requests_in_flight():
    in_flight = 0
    peak = 0

    async def endpoint(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return PlainTextResponse("ok")

    app = ConcurrencyLimitMiddleware(Starlette(routes=[Route("/", endpoint)]), limit=3)

    async def burst():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await asyncio.gather(*[client.get("/") for _ in range(20)])

    responses = asyncio.run(burst())
    assert all(r.status_code == 200 for r in responses)
    assert peak == 3
