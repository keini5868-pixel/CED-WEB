import { NextResponse } from "next/server";

import { apiUrl } from "@/lib/env";

const WEB_BUILD = "trial-15-pool-v15";

/** Diagnóstico BFF: comprueba que el web alcanza la API (sin auth). */
export async function GET() {
  const apiBase = apiUrl();

  try {
    const res = await fetch(`${apiBase}/health`, { cache: "no-store" });
    return NextResponse.json({
      ok: res.ok,
      web_build: WEB_BUILD,
      api_status: res.status,
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        web_build: WEB_BUILD,
      },
      { status: 502 },
    );
  }
}
