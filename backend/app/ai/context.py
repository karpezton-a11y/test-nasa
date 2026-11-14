"""Share the per-app explanation service with Karnish's unchanged PDF hook."""
from contextvars import ContextVar

REPORT_CONTEXT = ContextVar("trendtrace_report_explanation", default=None)


class ExplanationContextMiddleware:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        app = scope["app"]
        info = app.state.store.info
        token = REPORT_CONTEXT.set((app.state.explanations, info))
        try:
            await self.app(scope, receive, send)
        finally:
            REPORT_CONTEXT.reset(token)
