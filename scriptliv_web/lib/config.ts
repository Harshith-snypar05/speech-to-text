/**
 * Environment-based configuration. Nothing here hardcodes a backend address.
 *
 * NEXT_PUBLIC_WS_URL  browser -> relay WebSocket, e.g. ws://host:port   (required for live transcription)
 * SL_BACKEND_HTTP    server-side only: where Next proxies /sl/* (see next.config.ts)
 */
export const config = {
  wsUrl: process.env.NEXT_PUBLIC_WS_URL ?? "",
  /** ScriptLiv API base. Empty = same-origin /sl proxy (see next.config.ts). */
  slApiBase: process.env.NEXT_PUBLIC_SL_API_BASE ?? "",
  appName: "ScriptLiv",
};

export const isWsConfigured = () => config.wsUrl.length > 0;
