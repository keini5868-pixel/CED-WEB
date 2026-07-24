import type { MetadataRoute } from "next";

/** Dominio canónico público — no usar NEXT_PUBLIC_APP_URL (Railway). */
const SITE_URL = "https://ced-castillo.com";

/** robots.txt — apunta al sitemap para Search Console / crawlers. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/pricing", "/privacy", "/terms", "/login", "/signup"],
        disallow: [
          "/admin",
          "/dashboard",
          "/historial",
          "/drive",
          "/app",
          "/dev",
          "/api",
          "/verify-email",
          "/reset-password",
          "/forgot-password",
        ],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
