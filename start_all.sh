#!/usr/bin/env bash
# start_all.sh — Kill everything, then start API + relay + Next.js + Caddy + ngrok.
# Run from anywhere: bash /path/to/STT/start_all.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RELAY_PY="$ROOT/stt-compare-venv/bin/python3"
API_PY="$ROOT/scriptliv_api/.venv/bin/python3"
NPM=/opt/homebrew/bin/npm
CADDY=/opt/homebrew/bin/caddy
NGROK=/usr/local/bin/ngrok

NGROK_DOMAIN="ouch-devouring-unhelpful.ngrok-free.dev"
CADDY_PORT=5600
WEB_PORT=3100

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

# ── 1. KILL EXISTING PROCESSES ────────────────────────────────────────────────
echo "⏹  Stopping existing processes..."
pkill -f "parakeet_relay.py"   2>/dev/null || true
pkill -f "run_staging.py"      2>/dev/null || true
pkill -f "next dev"            2>/dev/null || true
pkill -f "next-server"         2>/dev/null || true
pkill -f "caddy run"           2>/dev/null || true
pkill -f "ngrok"               2>/dev/null || true
sleep 2
echo "   Done."

# ── 2. SCRIPTLIV API  (port 8790) ─────────────────────────────────────────────
echo "🚀 Starting API (port 8790)..."
"$API_PY" "$ROOT/scriptliv_api/run_staging.py" \
  > "$LOG_DIR/api.log" 2>&1 &
API_PID=$!
echo "   PID $API_PID → logs/api.log"

# ── 3. RELAY  (port 8772) ─────────────────────────────────────────────────────
echo "🎙  Starting relay (port 8772)..."
cd "$ROOT/relays_phase7c"
STT_LISTEN_PORT=8772 "$RELAY_PY" parakeet_relay.py \
  > "$LOG_DIR/relay.log" 2>&1 &
RELAY_PID=$!
cd "$ROOT"
echo "   PID $RELAY_PID → logs/relay.log"

# ── 4. NEXT.JS FRONTEND  (port 3100) ──────────────────────────────────────────
echo "🌐 Starting Next.js (port $WEB_PORT)..."
cd "$ROOT/scriptliv_web"
"$NPM" run dev -- --port "$WEB_PORT" \
  > "$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!
cd "$ROOT"
echo "   PID $WEB_PID → logs/web.log"

# ── 5. CADDY  (port 5600 → routes relay + Next.js) ────────────────────────────
echo "🔀 Starting Caddy (port $CADDY_PORT)..."
"$CADDY" run --config "$ROOT/Caddyfile" \
  > "$LOG_DIR/caddy.log" 2>&1 &
CADDY_PID=$!
echo "   PID $CADDY_PID → logs/caddy.log"

# ── 6. WAIT FOR SERVICES TO BE READY ─────────────────────────────────────────
echo ""
echo "⏳ Waiting for services to come up..."
for i in $(seq 1 30); do
  api_ok=false; web_ok=false
  curl -sf http://127.0.0.1:8790/healthz >/dev/null 2>&1 && api_ok=true
  curl -sf http://127.0.0.1:$WEB_PORT    >/dev/null 2>&1 && web_ok=true
  if $api_ok && $web_ok; then
    echo "   ✅ API and web ready (${i}s)"
    break
  fi
  printf "   [%2ds] api=%s web=%s\r" "$i" "$api_ok" "$web_ok"
  sleep 1
done
echo ""

# ── 7. NGROK  (tunnel Caddy port → fixed domain) ──────────────────────────────
echo "🌍 Starting ngrok tunnel → https://$NGROK_DOMAIN"
"$NGROK" http "$CADDY_PORT" \
  --domain="$NGROK_DOMAIN" \
  --log=stdout \
  > "$LOG_DIR/ngrok.log" 2>&1 &
NGROK_PID=$!
sleep 2
echo "   PID $NGROK_PID → logs/ngrok.log"

# ── 8. SUMMARY ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  API     http://127.0.0.1:8790    (PID $API_PID)"
echo "  Relay   ws://127.0.0.1:8772      (PID $RELAY_PID)"
echo "  Web     http://localhost:$WEB_PORT      (PID $WEB_PID)"
echo "  Caddy   http://localhost:$CADDY_PORT      (PID $CADDY_PID)"
echo "  ngrok   https://$NGROK_DOMAIN  (PID $NGROK_PID)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Public URL: https://$NGROK_DOMAIN"
echo ""
echo "Press Ctrl+C to stop everything."

# ── 9. WAIT & CLEANUP ON EXIT ─────────────────────────────────────────────────
trap 'echo ""; echo "🛑 Shutting down..."; kill $API_PID $RELAY_PID $WEB_PID $CADDY_PID $NGROK_PID 2>/dev/null; echo "Done."; exit 0' INT TERM

wait

