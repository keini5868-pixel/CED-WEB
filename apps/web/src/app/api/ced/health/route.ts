import { NextResponse } from "next/server";

import { apiUrl } from "@/lib/env";

const WEB_BUILD = "user-trash-historial-finanzas-v8";

/** Diagnóstico BFF: comprueba que el web alcanza la API (sin auth). */
export async function GET() {
  const apiBase = apiUrl();

  try {
    const res = await fetch(`${apiBase}/health`, { cache: "no-store" });
    const body = await res.text();
    let parsed: unknown = body;
    try {
      parsed = JSON.parse(body);
    } catch {
      /* raw text */
    }
    return NextResponse.json({
      ok: res.ok,
      web_build: WEB_BUILD,
      api_base: apiBase,
      api_status: res.status,
      api_response: parsed,
      hint: res.ok
        ? "Conexión web → API OK"
        : "Revisa NEXT_PUBLIC_API_URL en Railway (@ced/web) y redeploy",
    });
  } catch (err) {
    return NextResponse.json(
      {
        ok: false,
        api_base: apiBase,
        error: err instanceof Error ? err.message : String(err),
        hint: "NEXT_PUBLIC_API_URL debe apuntar al servicio API (ced-web-production)",
      },
      { status: 502 },
    );
  }
}
