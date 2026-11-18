import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * /sl/* is proxied (see next.config.ts rewrites) to SL_BACKEND_HTTP, which in this deployment is a free-tier
 * ngrok tunnel. ngrok serves an HTML "visit site" interstitial (ERR_NGROK_6024) instead of the real response
 * to requests that look like they came from a browser -- and Next's rewrite forwards the original browser's
 * User-Agent straight through. The documented bypass is this request header.
 */
export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("ngrok-skip-browser-warning", "true");
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/sl/:path*",
};
