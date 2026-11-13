/**
 * Environment-based configuration. Nothing here hardcodes a backend address.
 *
 * NEXT_PUBLIC_WS_URL  browser -> relay WebSocket, e.g. ws://host:port   (required for live transcription)
 * SL_BACKEND_HTTP    server-side only: where Next proxies /sl/* (see next.config.ts)
 */
// NEXT_PUBLIC_WS_URL is baked in at build time, which doesn't work behind a
// tunnel (ngrok, Cloudflare) whose public URL isn't known at build time and
// can change on every restart. When it's unset, fall back to the page's own
// origin at runtime -- this only works when the relay is proxied onto the
// same host/port as the web app (see the Caddy/reverse-proxy setup), same
// idea as the Flutter app's detectSameOriginBackendUrl.
function resolveWsUrl(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL;
  if (configured) return configured;
  if (typeof window === "undefined") return "";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}`;
}

export const config = {
  wsUrl: resolveWsUrl(),
  /** ScriptLiv API base. Empty = same-origin /sl proxy (see next.config.ts). */
  slApiBase: process.env.NEXT_PUBLIC_SL_API_BASE ?? "",
  appName: "ScriptLiv",
};

export const isWsConfigured = () => config.wsUrl.length > 0;
