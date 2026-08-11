import { createServerClient } from "@supabase/ssr";
import { NextRequest, NextResponse } from "next/server";

import { sanitizeAuthNext } from "@/lib/auth/paths";
import { apiUrl, isSupabaseConfigured } from "@/lib/env";

type CookieToSet = {
  name: string;
  value: string;
  options?: Record<string, unknown>;
};

function absoluteRedirect(request: NextRequest, path: string): string {
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? "https";
  if (forwardedHost) {
    return `${forwardedProto}://${forwardedHost}${path}`;
  }
  const { origin } = new URL(request.url);
  return `${origin}${path}`;
}

function stripOfferParam(path: string): string {
  try {
    const u = new URL(path, "https://ced.local");
    u.searchParams.delete("offer");
    const q = u.searchParams.toString();
    return `${u.pathname}${q ? `?${q}` : ""}${u.hash}`;
  } catch {
    return path;
  }
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = sanitizeAuthNext(searchParams.get("next"));
  const oauthError = searchParams.get("error");
  const oauthDescription = searchParams.get("error_description");

  if (!isSupabaseConfigured()) {
    return NextResponse.redirect(absoluteRedirect(request, "/login"));
  }

  if (oauthError) {
    console.error(
      "[AUTH:callback] OAuth provider error=%s desc=%s",
      oauthError,
      oauthDescription?.slice(0, 200) ?? "",
    );
    return NextResponse.redirect(absoluteRedirect(request, "/login?error=auth_callback"));
  }

  if (!code) {
    return NextResponse.redirect(absoluteRedirect(request, "/login?error=auth_callback"));
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

  let offer = "";
  try {
    offer = new URL(next, "https://ced.local").searchParams.get("offer")?.toLowerCase() || "";
  } catch {
    offer = "";
  }
  const cleanNext = stripOfferParam(next);
  const response = NextResponse.redirect(absoluteRedirect(request, cleanNext));

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: CookieToSet[]) {
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });
      },
    },
  });

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    console.error("[AUTH:callback] exchangeCodeForSession failed:", error.message);
    return NextResponse.redirect(absoluteRedirect(request, "/login?error=auth_callback"));
  }

  if (offer === "cierre" || offer === "fitline") {
    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const token = session?.access_token;
      if (token) {
        await fetch(`${apiUrl()}/v1/auth/apply-offer`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ offer: "cierre" }),
        });
      }
    } catch (exc) {
      console.error("[AUTH:callback] apply-offer failed:", exc);
    }
  }

  return response;
}
