import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import account_deletion
from .config import get_settings, production_problems
from .db import get_db
from .routers import account, admin, billing, internal, sessions, usage_routes

if os.environ.get("SCRIPTLIV_ENV", "").lower() == "production":
    _problems = production_problems()
    if _problems:
        raise RuntimeError("Refusing to start in production: " + "; ".join(_problems))

# Interactive docs / openapi.json list every route (incl. /internal/*); published only when explicitly enabled for local dev.
_DOCS = os.environ.get("SCRIPTLIV_ENABLE_DOCS", "").lower() in ("1", "true", "yes")
@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the bounded background sweep that finishes interrupted account deletions (see account_deletion.py). It is a
    daemon thread whose first run is one interval after start-up, so it never delays the API coming up."""
    stop = account_deletion.start_recovery_loop(get_db)
    try:
        yield
    finally:
        stop()


app = FastAPI(title="ScriptLiv API", version="0.1.0", lifespan=lifespan,
              docs_url="/docs" if _DOCS else None, redoc_url="/redoc" if _DOCS else None,
              openapi_url="/openapi.json" if _DOCS else None)

app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=False)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    d = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    return JSONResponse({"error": d}, status_code=exc.status_code)


_FIELD_HELP = {
    "email": "Enter a valid email address.",
    "new_email": "Enter a valid email address.",
    "password": "Enter your password.",
    "new_password": "Password must be at least 8 characters.",
    "current_password": "Enter your current password.",
    "name": "Enter a name (up to 80 characters).",
    "title": "Enter a title (up to 120 characters).",
}


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Turn pydantic's field report into one plain sentence a person can act on."""
    msg = "Some of the details look wrong. Check what you entered and try again."
    for e in exc.errors():
        field = next((str(x) for x in reversed(e.get("loc", ())) if isinstance(x, str) and x not in ("body", "query")), "")
        if field in _FIELD_HELP:
            msg = _FIELD_HELP[field]
            break
    return JSONResponse({"error": {"code": "invalid_input", "message": msg}}, status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    return JSONResponse({"error": {"code": "server_error", "message": "Something went wrong on our side. Nothing was lost; please try again in a moment."}}, status_code=500)


@app.get("/healthz")
def healthz():
    """Liveness plus a database round trip, so a load balancer stops routing to an instance that cannot reach MongoDB."""
    try:
        get_db().command("ping")
    except Exception:
        return JSONResponse({"ok": False, "db": "unreachable"}, status_code=503)
    return {"ok": True}


for r in (account.router, admin.router, billing.router, usage_routes.router, sessions.router, internal.router):
    app.include_router(r)
