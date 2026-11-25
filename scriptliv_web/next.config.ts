import type { NextConfig } from "next";

/** /sl/* is proxied to the ScriptLiv API (accounts, usage, billing, sessions). Set SL_BACKEND_HTTP, e.g. http://127.0.0.1:8790. */
const slBackend = process.env.SL_BACKEND_HTTP?.replace(/\/$/, "");

const isDev = process.env.NODE_ENV !== "production";

/**
 * Content-Security-Policy. Next.js emits inline bootstrap scripts and the layout sets the theme before paint, so
 * script-src keeps 'unsafe-inline' (a nonce policy would force every page to render dynamically). Everything else is
 * locked down: no framing (frame-ancestors), no plugins, no foreign base/form targets, and network access only to this
 * origin, secure WebSockets (the live relay) and Cashfree (payments, dormant while subscriptions are hidden).
 */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""} https://sdk.cashfree.com`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' wss: https://*.cashfree.com${isDev ? " ws: http://localhost:* http://127.0.0.1:*" : ""}`,
  "worker-src 'self' blob:",
  "media-src 'self' blob:",
  "frame-src https://*.cashfree.com",
  "frame-ancestors 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self' https://*.cashfree.com",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      ...(slBackend ? [{ source: "/sl/:path*", destination: `${slBackend}/:path*` }] : []),
    ];
  },
  async headers() {
    const noindex = [{ key: "X-Robots-Tag", value: "noindex, nofollow" }];
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=()" },
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
      // Account, token and transcript pages must never be indexed.
      ...["/app/:path*", "/s/:path*", "/reset-password", "/verify-email", "/forgot-password", "/sl/:path*"].map((source) => ({ source, headers: noindex })),
    ];
  },
};

export default nextConfig;
