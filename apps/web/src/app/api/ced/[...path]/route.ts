import { type NextRequest, NextResponse } from "next/server";

import { apiUrl } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

async function forward(request: NextRequest, pathSegments: string[]) {
  const supabase = await createClient();
  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return NextResponse.json({ detail: "Sin sesión" }, { status: 401 });
  }

  let token: string | undefined;
  const { data: sessionData } = await supabase.auth.getSession();
  token = sessionData.session?.access_token;

  if (!token) {
    const { data: refreshed } = await supabase.auth.refreshSession();
    token = refreshed.session?.access_token;
  }

  if (!token) {
    return NextResponse.json({ detail: "Sin sesión" }, { status: 401 });
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
    return NextResponse.json(
      {
        detail: `No se pudo contactar la API en ${apiUrl()}. ¿Está activa en Railway?`,
      },
      { status: 502 },
    );
  }

  const contentType = upstream.headers.get("content-type") || "application/json";
  const isBinary =
    contentType.includes("application/pdf") ||
    contentType.includes("application/octet-stream");

  if (isBinary) {
    const buffer = await upstream.arrayBuffer();
    return new NextResponse(buffer, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition":
          upstream.headers.get("content-disposition") || "attachment",
      },
    });
  }

  const responseBody = await upstream.text();
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: { "Content-Type": contentType },
  });
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
