#!/usr/bin/env bash
# stop_all.sh — Kill all ScriptLiv processes.
echo "🛑 Stopping all ScriptLiv processes..."
pkill -f "parakeet_relay.py" 2>/dev/null && echo "   relay stopped"    || true
pkill -f "run_staging.py"    2>/dev/null && echo "   API stopped"      || true
pkill -f "next dev"          2>/dev/null && echo "   Next.js stopped"  || true
pkill -f "next-server"       2>/dev/null                                || true
pkill -f "caddy run"         2>/dev/null && echo "   Caddy stopped"    || true
pkill -f "ngrok"             2>/dev/null && echo "   ngrok stopped"    || true
echo "Done."

