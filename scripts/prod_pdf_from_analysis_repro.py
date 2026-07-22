#!/usr/bin/env python3
"""Repro prod: PDF from prior long analysis — normal chat + advanced.

Confirms whether:
1) Normal chat: reply "completo" after clarify actually attaches a PDF
2) Advanced: PDF request returns attachment or generic technical error
3) Wallet/admin is blocking (needs_recharge) vs routing bug
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import httpx

API_BASE = "https://ced-web-production.up.railway.app"
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ANALYSIS = (
    "Análisis de mercado — figuras Dragon Ball Ultra Instinto (coleccionables):\n"
    "1) Demanda: fuerte en retail Amazon/Walmart y coleccionistas adult collectors.\n"
    "2) Precios típicos: $25–$120 según escala y licencia Bandai/Banpresto.\n"
    "3) Riesgos: stock limitado de ediciones, competencia de bootlegs, shipping.\n"
    "4) Oportunidad 6 meses: lanzamientos aniversario y bundles con accesorios.\n"
    "5) Canales: e-commerce, ferias anime, reventa certificada.\n"
    "Conclusión: nicho viable si se ancla a figuras oficiales, no tokens cripto."
)


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (REPO_ROOT / "apps/api/.env", REPO_ROOT / "apps/web/.env.local"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _get_access_token(env: dict[str, str], email: str = "keini5868@gmail.com") -> str:
    url = env["SUPABASE_URL"].rstrip("/")
    service = env["SUPABASE_SERVICE_ROLE_KEY"]
    adm = {
        "apikey": service,
        "Authorization": f"Bearer {service}",
        "Content-Type": "application/json",
    }
    link_res = httpx.post(
        f"{url}/auth/v1/admin/generate_link",
        headers=adm,
        json={"type": "magiclink", "email": email},
        timeout=30,
    )
    link_res.raise_for_status()
    action_link = link_res.json()["action_link"]
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        verify = client.get(action_link)
    location = verify.headers.get("location", "")
    match = re.search(r"access_token=([^&]+)", location)
    if not match:
        raise RuntimeError("No se pudo obtener access_token")
    return match.group(1)


def _parse_sse(res: httpx.Response) -> dict:
    events: list[dict] = []
    done: dict | None = None
    buffer = ""
    t0 = time.perf_counter()
    last = t0
    max_gap = 0.0
    first_byte = None
    for chunk in res.iter_text():
        now = time.perf_counter()
        if first_byte is None:
            first_byte = now - t0
        max_gap = max(max_gap, now - last)
        last = now
        buffer += chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            if not block.strip():
                continue
            name = "message"
            data = ""
            for line in block.split("\n"):
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
            if not data:
                events.append({"t": round(now - t0, 2), "event": name})
                continue
            try:
                parsed = json.loads(data)
            except Exception:
                parsed = {"raw": data[:160]}
            row: dict = {"t": round(now - t0, 2), "event": name}
            if name == "token":
                row["text"] = str(parsed.get("text") or "")[:120]
            elif name == "status":
                row["text"] = str(parsed.get("text") or "")[:120]
            elif name == "done":
                done = parsed
                row["has_pdf"] = bool((parsed.get("pdf") or {}).get("file_id"))
                row["reply"] = str(parsed.get("reply") or parsed.get("response") or "")[:180]
                row["recharge"] = parsed.get("recharge_needed")
            events.append(row)
    return {
        "http": res.status_code,
        "first_byte_s": round(first_byte, 2) if first_byte else None,
        "max_gap_s": round(max_gap, 2),
        "total_s": round(time.perf_counter() - t0, 2),
        "events": events,
        "done": done,
    }


def stream_normal(client: httpx.Client, token: str, content: str, conv_id: str | None) -> dict:
    body: dict = {"content": content}
    if conv_id:
        body["conversation_id"] = conv_id
    with client.stream(
        "POST",
        "/v1/chat/send/stream",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json=body,
    ) as res:
        out = _parse_sse(res)
    done = out.get("done") or {}
    out["conv_id"] = done.get("conversation_id") or conv_id
    out["has_pdf"] = bool((done.get("pdf") or {}).get("file_id"))
    out["reply"] = str(done.get("reply") or "")[:240]
    out["recharge"] = done.get("recharge_needed")
    return out


def stream_advanced(
    client: httpx.Client, token: str, message: str, history: list[dict]
) -> dict:
    with client.stream(
        "POST",
        "/v1/advanced/chat/stream",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        json={"message": message, "history": history},
    ) as res:
        out = _parse_sse(res)
    done = out.get("done") or {}
    out["has_pdf"] = bool((done.get("pdf") or {}).get("file_id"))
    out["reply"] = str(done.get("response") or done.get("reply") or "")[:240]
    out["recharge"] = done.get("recharge_needed")
    return out


def dump(label: str, result: dict) -> None:
    print(f"\n=== {label} ===")
    for ev in result.get("events") or []:
        print(" ", json.dumps(ev, ensure_ascii=False))
    summary = {
        k: result.get(k)
        for k in (
            "http",
            "first_byte_s",
            "max_gap_s",
            "total_s",
            "has_pdf",
            "reply",
            "recharge",
            "conv_id",
        )
        if k in result
    }
    print(" SUMMARY", json.dumps(summary, ensure_ascii=False))


def main() -> int:
    env = _load_env()
    token = _get_access_token(env)
    print(f"API={API_BASE} build check…")
    health = httpx.get(f"{API_BASE}/health", timeout=30).json()
    print(" build=", health.get("build"))

    with httpx.Client(base_url=API_BASE, timeout=httpx.Timeout(300.0, connect=30.0)) as client:
        # --- Normal chat path ---
        print("\n######## NORMAL CHAT ########")
        r1 = stream_normal(
            client,
            token,
            f"Dame un análisis breve de este mercado:\n\n{ANALYSIS}",
            None,
        )
        dump("1) seed analysis", r1)
        conv = r1.get("conv_id")

        r2 = stream_normal(
            client, token, "genera un pdf con esa información", conv
        )
        dump("2) ask PDF", r2)

        r3 = stream_normal(client, token, "completo", conv)
        dump("3) answer completo (critical)", r3)

        # --- Advanced path ---
        print("\n######## ADVANCED ########")
        hist = [
            {"role": "user", "content": "Analiza el mercado de figuras Dragon Ball"},
            {"role": "assistant", "content": ANALYSIS},
        ]
        a1 = stream_advanced(
            client, token, "genera un pdf con esa información", hist
        )
        dump("A1) ask PDF advanced", a1)
        hist2 = hist + [
            {"role": "user", "content": "genera un pdf con esa información"},
            {
                "role": "assistant",
                "content": a1.get("reply")
                or "¿Prefiere un resumen breve o el contenido completo para el PDF, señor?",
            },
        ]
        a2 = stream_advanced(client, token, "completo", hist2)
        dump("A2) completo advanced", a2)

    print("\n######## VERDICT ########")
    print(
        "normal_completo_has_pdf=",
        r3.get("has_pdf"),
        "reply_snip=",
        (r3.get("reply") or "")[:100],
    )
    print(
        "advanced_ask_has_pdf=",
        a1.get("has_pdf"),
        "reply_snip=",
        (a1.get("reply") or "")[:100],
    )
    print(
        "advanced_completo_has_pdf=",
        a2.get("has_pdf"),
        "reply_snip=",
        (a2.get("reply") or "")[:100],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
