"""Serves the built Flutter web app AND proxies WebSocket connections to
a relay, both on one port -- so a single Cloudflare tunnel (or any single
public URL) covers the whole app with no per-device backend URL setup.

Any request carrying `role=speaker` or `role=viewer` in its query string
is treated as a relay connection and proxied through (bidirectional,
binary-safe) to the real relay on RELAY_PORT. Everything else is served
as a static file from build/web, falling back to index.html for
Flutter's client-side hash routing.

Usage:
    python3 relays/combined_proxy.py [--relay-port 8767] [--listen-port 5501] [--web-dir st_transcribe_app/build/web]
"""
import argparse
import asyncio
import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

import websockets
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("combined_proxy")

ROOT = Path(__file__).resolve().parent.parent


def make_process_request(web_dir: Path):
    def process_request(connection, request):
        query = urlsplit(request.path).query
        if "role=speaker" in query or "role=viewer" in query:
            return None  # let the websocket handshake proceed -> proxied

        url_path = urlsplit(request.path).path
        rel = url_path.lstrip("/") or "index.html"
        candidate = (web_dir / rel).resolve()
        if not str(candidate).startswith(str(web_dir.resolve())) or not candidate.is_file():
            candidate = web_dir / "index.html"  # SPA fallback

        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        headers = Headers([("Content-Type", content_type), ("Content-Length", str(len(body)))])
        return Response(200, "OK", headers, body)

    return process_request


def make_handler(relay_port: int):
    async def handler(connection):
        # Only reached for connections process_request let through -- i.e.
        # genuine relay traffic. Open a matching connection to the real
        # relay and pipe both directions until either side closes.
        backend_uri = f"ws://localhost:{relay_port}{connection.request.path}"
        logger.info(f"proxying {connection.request.path} -> {backend_uri}")
        try:
            async with websockets.connect(backend_uri, max_size=None) as backend:
                logger.info(f"backend connection established for {connection.request.path}")

                async def client_to_backend():
                    try:
                        async for message in connection:
                            await backend.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    finally:
                        # The browser disconnecting must be visible to the
                        # relay as a real disconnect (not just "no more
                        # messages for now"), or its own flush-on-disconnect
                        # logic (the one guaranteeing the last utterance
                        # isn't dropped) never runs.
                        await backend.close()

                async def backend_to_client():
                    try:
                        async for message in backend:
                            await connection.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    finally:
                        await connection.close()

                await asyncio.gather(client_to_backend(), backend_to_client(), return_exceptions=True)
        except Exception as e:
            logger.exception(f"proxy failed for {backend_uri}: {e}")
            try:
                await connection.close(code=1011, reason="backend unavailable")
            except Exception:
                pass

    return handler


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--relay-port", type=int, default=8767)
    parser.add_argument("--listen-port", type=int, default=5501)
    parser.add_argument("--web-dir", default=str(ROOT / "st_transcribe_app" / "build" / "web"))
    args = parser.parse_args()

    web_dir = Path(args.web_dir).resolve()
    if not web_dir.is_dir():
        raise SystemExit(f"web build not found at {web_dir} -- run `flutter build web` first")

    async with serve(
        make_handler(args.relay_port),
        "0.0.0.0",
        args.listen_port,
        process_request=make_process_request(web_dir),
        max_size=None,
    ):
        logger.info(f"combined proxy listening on http://localhost:{args.listen_port} "
                     f"(web: {web_dir}, relay: ws://localhost:{args.relay_port})")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
