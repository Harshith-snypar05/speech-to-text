import type { MetadataRoute } from "next";

const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://scriptliv.com").replace(/\/$/, "");

/** Public marketing pages are crawlable; the signed-in app, API proxy, shared transcripts and token links are not. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/app", "/app/", "/s/", "/sl/", "/reset-password", "/verify-email", "/forgot-password"] }],
    sitemap: `${SITE}/sitemap.xml`,
    host: SITE,
  };
}
