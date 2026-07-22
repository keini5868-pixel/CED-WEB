import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { apiUrl } from "@/lib/env";

/** Generación con imagen adjunta puede tardar varios minutos (Gemini). */
export const maxDuration = 300;

type CookieToSet = {
  name: string;
  value: string;
  options?: Record<string, unknown>;
};

function createClientFromRequest(
  request: NextRequest,
  response: NextResponse,
) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  return createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: CookieToSet[]) {
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });
}

function bearerFromRequest(request: NextRequest): string | null {
  const raw = request.headers.get("authorization")?.trim();
  if (!raw || !raw.toLowerCase().startsWith("bearer ")) {
    return null;
  }
  const token = raw.slice(7).trim();
  return token || null;
}

async function resolveAccessToken(
  request: NextRequest,
): Promise<{ token: string | null; authResponse: NextResponse }> {
  const headerToken = bearerFromRequest(request);
  if (headerToken) {
    return { token: headerToken, authResponse: new NextResponse() };
  }

  const authResponse = new NextResponse();
  const supabase = createClientFromRequest(request, authResponse);

  const { data: sessionData } = await supabase.auth.getSession();
  if (sessionData.session?.access_token) {
    return { token: sessionData.session.access_token, authResponse };
  }

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();
  if (userError || !user) {
    return { token: null, authResponse };
  }

  const { data: refreshed, error: refreshError } =
    await supabase.auth.refreshSession();
  if (!refreshError && refreshed.session?.access_token) {
    return { token: refreshed.session.access_token, authResponse };
  }

  const { data: retry } = await supabase.auth.getSession();
  return {
    token: retry.session?.access_token ?? null,
    authResponse,
  };
}

function mergeAuthCookies(
  target: NextResponse,
  authResponse: NextResponse,
): NextResponse {
  authResponse.cookies.getAll().forEach((cookie) => {
    target.cookies.set(cookie);
  });
  return target;
}

function isLongRunningChatPath(path: string): boolean {
  const normalized = path.toLowerCase();
  return (
    normalized.includes("chat/send-with-image") ||
    normalized.includes("chat/send/stream") ||
    normalized.includes("advanced/chat") ||
    normalized.includes("finance/chat") ||
    normalized.includes("viability-pilot/analyze") ||
    normalized.includes("trends-pilot/analyze") ||
    normalized.includes("opportunities-pilot/opportunities") ||
    normalized.includes("images/generate-with-reference") ||
    normalized.includes("images/generate") ||
    normalized.includes("vision/") ||
    normalized.includes("hud/life")
  );
}

/** Google Calendar/Gmail — cold start Railway puede tardar. */
function isHudGooglePath(path: string): boolean {
  const normalized = path.toLowerCase();
  return (
    normalized.includes("hud/calendar") ||
    normalized.includes("hud/gmail") ||
    normalized.includes("hud/connections")
  );
}

async function forward(request: NextRequest, pathSegments: string[]) {
  const { token, authResponse } = await resolveAccessToken(request);

  if (!token) {
    return mergeAuthCookies(
      NextResponse.json({ detail: "Sin sesión" }, { status: 401 }),
      authResponse,
    );
  }

  const path = pathSegments.map(encodeURIComponent).join("/");
  const search = request.nextUrl.search;
  const target = `${apiUrl()}/v1/${path}${search}`;

  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
  };
  const requestContentType = request.headers.get("content-type");
  if (requestContentType) {
    headers["Content-Type"] = requestContentType;
  }
  const ephemeralKey = request.headers.get("x-openai-ephemeral-key");
  if (ephemeralKey) {
    headers["X-OpenAI-Ephemeral-Key"] = ephemeralKey;
  }
    const viabilityPilot = request.headers.get("x-ced-viability-pilot");
  if (viabilityPilot) {
    headers["X-CED-Viability-Pilot"] = viabilityPilot;
  }
  const trendsPilot = request.headers.get("x-ced-trends-pilot");
  if (trendsPilot) {
    headers["X-CED-Trends-Pilot"] = trendsPilot;
  }
  const opportunitiesPilot = request.headers.get("x-ced-opportunities-pilot");
  if (opportunitiesPilot) {
    headers["X-CED-Opportunities-Pilot"] = opportunitiesPilot;
  }

  let body: BodyInit | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    if (requestContentType?.includes("multipart/form-data")) {
      body = await request.arrayBuffer();
    } else {
      body = await request.text();
    }
  }

  let upstream: Response;
  const timeoutMs = isLongRunningChatPath(path)
    ? 300_000
    : isHudGooglePath(path)
      ? 120_000
      : 60_000;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    const timedOut =
      err instanceof Error &&
      (err.name === "TimeoutError" || err.name === "AbortError");
    return mergeAuthCookies(
      NextResponse.json(
        {
          detail: timedOut
            ? "La operación tardó demasiado. Reintenta en unos segundos."
            : `No se pudo contactar la API en ${apiUrl()}. ¿Está activa en Railway?`,
        },
        { status: timedOut ? 504 : 502 },
      ),
      authResponse,
    );
  }

  const contentType = upstream.headers.get("content-type") || "application/json";
  const isBinary =
    contentType.includes("application/pdf") ||
    contentType.includes("application/octet-stream") ||
    contentType.includes("application/sdp") ||
    contentType.startsWith("image/");

  if (isBinary) {
    const buffer = await upstream.arrayBuffer();
    return mergeAuthCookies(
      new NextResponse(buffer, {
        status: upstream.status,
        headers: {
          "Content-Type": contentType,
          "Content-Disposition":
            upstream.headers.get("content-disposition") || "attachment",
        },
      }),
      authResponse,
    );
  }

  const responseBody = await upstream.text();
  return mergeAuthCookies(
    new NextResponse(responseBody, {
      status: upstream.status,
      headers: { "Content-Type": contentType },
    }),
    authResponse,
  );
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forward(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forward(request, path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forward(request, path);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forward(request, path);
}
