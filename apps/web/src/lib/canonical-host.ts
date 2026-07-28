import { NextRequest, NextResponse } from "next/server";

import { PRODUCTION_WEB_URL } from "@/lib/env";

const CANONICAL_HOST = "ced-castillo.com";

/**
 * 301 permanente a https://ced-castillo.com (sin www, sin http).
 * Usa x-forwarded-* de Railway para no pegar :8080 en el Location.
 */
export function redirectToCanonicalHost(
  request: NextRequest,
): NextResponse | null {
  const rawHost =
    request.headers.get("x-forwarded-host") ||
    request.headers.get("host") ||
    "";
  const forwardedHost = (rawHost.split(",")[0] ?? rawHost).trim().toLowerCase();

  // Quitar puerto interno (Railway a veces expone :8080)
  const host = forwardedHost.replace(/:\d+$/, "");
  if (!host || host === "localhost" || host.endsWith(".railway.app")) {
    return null;
  }

  const rawProto =
    request.headers.get("x-forwarded-proto") ||
    request.nextUrl.protocol.replace(":", "") ||
    "https";
  const forwardedProto = (rawProto.split(",")[0] ?? rawProto)
    .trim()
    .toLowerCase();

  const isWww = host === `www.${CANONICAL_HOST}`;
  const isApex = host === CANONICAL_HOST;
  const isLegacy = host.includes("castillodigital.com");
  const needsHttps = isApex && forwardedProto === "http";

  if (!isWww && !isLegacy && !needsHttps) {
    return null;
  }

  const path = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  const target = `${PRODUCTION_WEB_URL}${path === "/" ? "/" : path}`;
  return NextResponse.redirect(target, 301);
}
