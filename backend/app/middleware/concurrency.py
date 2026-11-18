"""Cap the number of requests inside the app at the database pool size.

A sync FastAPI request makes two trips through the 40-thread pool: one for
its dependencies (get_current_user loads the user, which checks out a
connection) and one for the route itself, holding the connection in between.
Under a burst of more than ~55 requests every thread can end up waiting for a
connection while every connection belongs to a request waiting for a thread,
and all of them hang until the 30 s pool timeout. Letting at most as many
requests in as there are connections makes that impossible; the rest wait
here briefly instead.
"""

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send


class ConcurrencyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit
        self._semaphore: asyncio.Semaphore | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if self._semaphore is None:
            # Created lazily so it binds to the server's event loop
            self._semaphore = asyncio.Semaphore(self.limit)
        # Held until the inner app returns: after the response, the cleanup
        # that returns the connection and any background tasks
        async with self._semaphore:
            await self.app(scope, receive, send)
