"""Start the ScriptLiv relay for staging. Loads staging_secrets/api.env (never printed), then launches supervisor.py."""
import os
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parent.parent
env_file = root / "staging_secrets" / "api.env"

for line in env_file.read_text(encoding="utf8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

# Now launch the supervisor (or parakeet_relay directly) with the env loaded.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

if __name__ == "__main__":
    import supervisor
    supervisor.main()

