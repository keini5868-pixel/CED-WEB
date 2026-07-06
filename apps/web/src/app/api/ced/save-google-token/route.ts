import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { apiUrl } from "@/lib/env";

type CookieToSet = {
  name: string;
  value: string;
  options?: Record<string, unknown>;
};

async function resolveAccessToken(
  request: NextRequest,
): Promise<{ token: string | null; authResponse: NextResponse }> {
  const raw = request.headers.get("authorization")?.trim();
  if (raw?.toLowerCase().startsWith("bearer ")) {
    const token = raw.slice(7).trim();
    if (token) {
      return { token, authResponse: new NextResponse() };
    }
  }

  const authResponse = new NextResponse();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          cookiesToSet.forEach(({ name, value, options }) =>
            authResponse.cookies.set(name, value, options),
          );
        },
      },
    },
  );

  const { data: sessionData } = await supabase.auth.getSession();
  return {
    token: sessionData.session?.access_token ?? null,
    authResponse,
  };
}

/** Persiste provider_token de Supabase Auth en calendar_tokens / gmail_tokens (API). */
export async function POST(request: NextRequest) {
  const { token, authResponse } = await resolveAccessToken(request);
  if (!token) {
    return NextResponse.json({ detail: "Sin sesión" }, { status: 401 });
  }

  const body = await request.text();
  const target = `${apiUrl()}/v1/google/save-token`;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    return NextResponse.json(
      { detail: `No se pudo contactar la API en ${apiUrl()}.` },
      { status: 502 },
    );
  }

  const contentType = upstream.headers.get("content-type") || "application/json";
  const responseBody = await upstream.text();
  const response = new NextResponse(responseBody, {
    status: upstream.status,
    headers: { "Content-Type": contentType },
  });
  authResponse.cookies.getAll().forEach((cookie) => {
    response.cookies.set(cookie);
  });
  return response;
}
