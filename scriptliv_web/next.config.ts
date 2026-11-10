import type { NextConfig } from "next";

/** /sl/* is proxied to the ScriptLiv API (accounts, usage, billing, sessions). Set SL_BACKEND_HTTP, e.g. http://127.0.0.1:8790. */
const slBackend = process.env.SL_BACKEND_HTTP?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      ...(slBackend ? [{ source: "/sl/:path*", destination: `${slBackend}/:path*` }] : []),
    ];
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "no-referrer" },
        { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=()" },
      ],
    }];
  },
};

export default nextConfig;
