"""Verifica Site URL / redirects de Supabase Auth (sin secrets en stdout).

Uso (con vars de Railway API cargadas o env local):
  python scripts/_verify_supabase_auth_urls.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL = "https://ced-castillo.com"
FORBIDDEN_HOST = "castillodigital.com"


def _railway_vars() -> dict:
    out = subprocess.check_output(
        [
            "npx",
            "--yes",
            "@railway/cli@latest",
            "variable",
            "list",
            "--json",
            "-s",
            "CED-WEB",
            "-e",
            "production",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )
    return json.loads(out)


def main() -> int:
    rail = _railway_vars()
    url = (rail.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = (
        rail.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not url or not key:
        print("MISSING Supabase URL/key")
        return 1

    r = httpx.post(
        f"{url}/auth/v1/admin/generate_link",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "type": "recovery",
            "email": "keini5868@gmail.com",
            "options": {
                "redirect_to": f"{CANONICAL}/auth/callback?next=/reset-password"
            },
        },
        timeout=30,
    )
    d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    redirect = d.get("redirect_to") or (d.get("properties") or {}).get("redirect_to") or ""
    action = d.get("action_link") or (d.get("properties") or {}).get("action_link") or ""

    print("generate_link_status", r.status_code)
    print("redirect_to", redirect)
    print("action_has_forbidden_host", FORBIDDEN_HOST in (action + redirect))
    print("site_url_is_canonical", redirect.startswith(CANONICAL))

    asked = f"{CANONICAL}/auth/callback?next=/reset-password"
    accepted = urllib.parse.unquote(redirect) == asked or redirect == asked
    print("path_redirect_accepted", accepted)
    if not accepted:
        print(
            "NOTE: Redirect allowlist aún no acepta /auth/callback — "
            "añádelo en Supabase → Authentication → URL Configuration. "
            "Mientras tanto Site URL canónico + middleware reenvían ?code=."
        )

    print("RESEND_API_KEY", "SET" if rail.get("RESEND_API_KEY") else "MISSING")
    print("EMAIL_FROM", rail.get("EMAIL_FROM"))
    print("WEB_PUBLIC_URL", rail.get("WEB_PUBLIC_URL"))
    return 0 if redirect.startswith(CANONICAL) and FORBIDDEN_HOST not in (action + redirect) else 2


if __name__ == "__main__":
    sys.exit(main())
