import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

import { apiUrl } from "@/lib/env";

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

async function resolveAccessToken(
  request: NextRequest,
): Promise<{ token: string | null; authResponse: NextResponse }> {
  const authResponse = new NextResponse();
  const supabase = createClientFromRequest(request, authResponse);

  const { data: sessionData } = await supabase.auth.getSession();
  if (sessionData.session?.access_token) {
    return { token: sessionData.session.access_token, authResponse };
  }

  const { data: refreshed } = await supabase.auth.refreshSession();
  if (refreshed.session?.access_token) {
    return { token: refreshed.session.access_token, authResponse };
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return { token: null, authResponse };
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

  let body: string | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.text();
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
  } catch {
    return mergeAuthCookies(
      NextResponse.json(
        {
          detail: `No se pudo contactar la API en ${apiUrl()}. ¿Está activa en Railway?`,
        },
        { status: 502 },
      ),
      authResponse,
    );
  }

  const contentType = upstream.headers.get("content-type") || "application/json";
  const isBinary =
    contentType.includes("application/pdf") ||
    contentType.includes("application/octet-stream");

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
