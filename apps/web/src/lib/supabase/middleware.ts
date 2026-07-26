import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { isSuperAdmin } from "@/lib/auth/roles";
import {
  ADMIN_PATH,
  DASHBOARD_PATH,
  RESET_PASSWORD_PATH,
  PUBLIC_AUTH_PREFIXES,
  PROTECTED_PREFIXES,
  sanitizeAuthNext,
} from "@/lib/auth/paths";

type CookieToSet = {
  name: string;
  value: string;
  options?: Record<string, unknown>;
};

function matchesPrefix(pathname: string, prefixes: readonly string[]) {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Si Supabase Site URL acepta el redirect pero la allowlist no incluye el path
 * (p.ej. /auth/callback), el código PKCE aterriza en `/`. Reenviamos al
 * callback con el destino correcto (recovery → reset-password).
 */
function redirectAuthCodeIfNeeded(request: NextRequest): NextResponse | null {
  const pathname = request.nextUrl.pathname;
  if (pathname.startsWith("/auth/callback") || pathname.startsWith("/api/")) {
    return null;
  }
  const code = request.nextUrl.searchParams.get("code");
  if (!code) return null;

  const authType = (request.nextUrl.searchParams.get("type") || "").toLowerCase();
  const nextParam = request.nextUrl.searchParams.get("next");
  let next = sanitizeAuthNext(nextParam, DASHBOARD_PATH);
  if (
    authType === "recovery" ||
    authType === "invite" ||
    pathname.startsWith(RESET_PASSWORD_PATH)
  ) {
    next = RESET_PASSWORD_PATH;
  }

  // /reset-password?code=… lo maneja ResetPasswordForm
  if (pathname.startsWith(RESET_PASSWORD_PATH)) {
    return null;
  }

  const target = request.nextUrl.clone();
  target.pathname = "/auth/callback";
  target.search = "";
  target.searchParams.set("code", code);
  target.searchParams.set("next", next);
  return NextResponse.redirect(target);
}

export async function updateSession(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  // Railway healthcheck — nunca bloquear por Supabase
  if (pathname === "/health" || pathname === "/api/ced/health") {
    return NextResponse.next({ request });
  }

  const authCodeRedirect = redirectAuthCodeIfNeeded(request);
  if (authCodeRedirect) {
    return authCodeRedirect;
  }

  let supabaseResponse = NextResponse.next({ request });

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key || url.includes("TU_PROYECTO")) {
    return supabaseResponse;
  }

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: CookieToSet[]) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value),
        );
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          supabaseResponse.cookies.set(name, value, options),
        );
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (
    process.env.NODE_ENV === "development" &&
    pathname.startsWith("/dev")
  ) {
    return supabaseResponse;
  }

  const isAuthRoute = matchesPrefix(pathname, PUBLIC_AUTH_PREFIXES);
  const isProtected = matchesPrefix(pathname, PROTECTED_PREFIXES);
  const isResetPassword = pathname.startsWith("/reset-password");

  if (!user && isProtected) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/login";
    const nextPath =
      pathname === "/app" ? DASHBOARD_PATH : pathname;
    redirectUrl.searchParams.set("next", nextPath);
    return NextResponse.redirect(redirectUrl);
  }

  if (
    user &&
    isAuthRoute &&
    !pathname.startsWith("/auth/callback") &&
    !isResetPassword &&
    !pathname.startsWith("/verify-email")
  ) {
    const next = sanitizeAuthNext(request.nextUrl.searchParams.get("next"));
    const target = new URL(next, request.url);
    return NextResponse.redirect(target);
  }

  if (user && pathname.startsWith(ADMIN_PATH)) {
    const metadataRole = user.app_metadata?.role as string | undefined;
    const { data: profile } = await supabase
      .from("profiles")
      .select("role")
      .eq("id", user.id)
      .maybeSingle();
    const profileRole = profile?.role as string | undefined;
    if (!isSuperAdmin(user.email, metadataRole, profileRole)) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = DASHBOARD_PATH;
      return NextResponse.redirect(redirectUrl);
    }
  }

  // Rutas /dev/* no deben ser públicas en producción.
  if (
    pathname.startsWith("/dev") &&
    process.env.NODE_ENV === "production"
  ) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/";
    return NextResponse.redirect(redirectUrl);
  }

  return supabaseResponse;
}
