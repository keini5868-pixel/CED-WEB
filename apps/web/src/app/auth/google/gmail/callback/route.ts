import { NextRequest, NextResponse } from "next/server";

const API_CALLBACK = "https://ced-web-production.up.railway.app/auth/google/gmail/callback";

/** Google vuelve al host web. La API intercambia el código y abre Correo. */
export function GET(request: NextRequest) {
  const target = new URL(API_CALLBACK);
  target.search = request.nextUrl.search;
  return NextResponse.redirect(target);
}
