import type { MetadataRoute } from "next";
import { SHOW_SUBSCRIPTIONS } from "@/lib/features";

const SITE = (process.env.NEXT_PUBLIC_SITE_URL || "https://scriptliv.com").replace(/\/$/, "");

/** Static public pages only. Never list /app, /s/<token> or any tokenized link. */
export default function sitemap(): MetadataRoute.Sitemap {
  const paths = ["/", "/login", "/register", "/terms", "/privacy", "/delete-data", ...(SHOW_SUBSCRIPTIONS ? ["/pricing"] : [])];
  return paths.map((p) => ({ url: SITE + (p === "/" ? "" : p), changeFrequency: p === "/" ? "weekly" : "monthly", priority: p === "/" ? 1 : 0.5 }));
}
