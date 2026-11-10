"""Start the ScriptLiv API for staging on 127.0.0.1:8790. Loads staging_secrets/api.env (never printed)."""
import os
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent
env = root.parent / "staging_secrets" / "api.env"
for line in env.read_text(encoding="utf8").splitlines():
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(root))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("SCRIPTLIV_API_PORT", "8790")), log_level="info")
