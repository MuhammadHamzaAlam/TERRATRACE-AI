from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analyses, assistant, model, projects, reports, satellite, system
from app.core.config import get_settings
from app.database.session import init_db
from app.jobs import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("terratrace")


def create_app() -> FastAPI:
    s = get_settings()
    @asynccontextmanager
    async def lifespan(_app):
        init_db()
        runner.mark_interrupted_jobs()
        yield

    app = FastAPI(title=s.app_name, version="1.0.0", lifespan=lifespan,
                  description="Geospatial change intelligence & infrastructure monitoring API")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
    hits: dict[str, deque] = defaultdict(deque)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        ip = request.client.host if request.client else "?"
        now = time.time(); q = hits[ip]
        while q and now - q[0] > 60: q.popleft()
        if len(q) >= s.rate_limit_per_minute and not request.url.path.endswith("/health"):
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        q.append(now)
        try:
            resp = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("unhandled error on %s", request.url.path)
            return JSONResponse({"detail": "Internal server error"}, status_code=500)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    for r in (system.router, projects.router, analyses.router, reports.router, model.router, satellite.router, assistant.router):
        app.include_router(r, prefix="/api")

    return app


app = create_app()
