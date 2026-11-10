import os

from fastapi import FastAPI, HTTPException, Request
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


@app.get("/healthz")
def healthz():
    return {"ok": True}


for r in (account.router, billing.router, usage_routes.router, sessions.router, internal.router):
    app.include_router(r)
