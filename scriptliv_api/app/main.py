import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import account, billing, internal, sessions, usage_routes

# Interactive docs / openapi.json list every route (incl. /internal/*); published only when explicitly enabled for local dev.
_DOCS = os.environ.get("SCRIPTLIV_ENABLE_DOCS", "").lower() in ("1", "true", "yes")
app = FastAPI(title="ScriptLiv API", version="0.1.0",
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
    return {"ok": True}


for r in (account.router, billing.router, usage_routes.router, sessions.router, internal.router):
    app.include_router(r)
