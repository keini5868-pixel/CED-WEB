"""Referidos CED — Referral ID + actividad de venta de invitados.

Propósito: que el socio vea quién de su equipo usa CED de verdad para vender
PM International (voz, chat de venta/prospección, Finanzas, OPPS), no actividad
genérica del sistema.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

ACTIVE_DAYS = 7
LOOKBACK_DAYS = 14
CODE_PREFIX = "CED"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SALES_CHAT_RE = re.compile(
    r"(?is)\b(?:"
    r"prospect\w*|prospecci[oó]n|vender|venta|franquicia|patrocin\w*|"
    r"socio(?:s)?\s+de\s+negocio|invitar\s+al\s+negocio|"
    r"cerrar\s+(?:la\s+)?venta|cierre|"
    r"pm[\s\-]?international|fitline|fit\s*line|"
    r"plan\s+de\s+compensaci[oó]n|paquete\s+manager"
    r")\b"
)

ACTIVITY_KINDS = frozenset(
    {"voice", "voice_pm", "chat_sales", "finance", "opps", "sponsor"}
)


def _client():
    from app.services import supabase_db

    return supabase_db._client()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_since(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat()


def generate_referral_code(user_id: str) -> str:
    raw = (user_id or "").replace("-", "").upper()
    if len(raw) >= 8:
        return f"{CODE_PREFIX}{raw[:8]}"
    return f"{CODE_PREFIX}{uuid4().hex[:8].upper()}"


def normalize_referral_code(raw: str | None) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip().upper())
    if code.startswith("CED") and 6 <= len(code) <= 16:
        return code
    if 4 <= len(code) <= 16:
        return f"CED{code}" if not code.startswith("CED") else code
    return ""


def normalize_pm_partner_id(raw: str | None) -> str:
    """ID de socio PM International (Partner Area). No antepone CED."""
    code = re.sub(r"\s+", "", (raw or "").strip())
    if 3 <= len(code) <= 40:
        return code
    return ""


def is_relevant_sales_chat(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 8:
        return False
    if _SALES_CHAT_RE.search(t):
        return True
    try:
        from app.services.opportunities_pilot.fitline_knowledge import (
            prefers_fitline_over_web,
            wants_fitline_knowledge,
        )

        return bool(wants_fitline_knowledge(t) or prefers_fitline_over_web(t))
    except Exception:  # noqa: BLE001
        return False


def display_name_from_profile(profile: dict[str, Any] | None) -> str:
    row = profile or {}
    full = str(row.get("full_name") or "").strip()
    if full:
        parts = [p for p in full.split() if p]
        if len(parts) == 1:
            return parts[0]
        return f"{parts[0]} {parts[-1][:1]}."
    email = str(row.get("email") or "").strip()
    if email and "@" in email:
        return email.split("@", 1)[0]
    return "Invitado"


def ensure_referral_code(user_id: str) -> str:
    uid = (user_id or "").strip()
    if not uid:
        return ""
    try:
        row = (
            _client()
            .table("profiles")
            .select("id, referral_code")
            .eq("id", uid)
            .limit(1)
            .execute()
        )
        data = (row.data or [None])[0] or {}
        existing = normalize_referral_code(str(data.get("referral_code") or ""))
        if existing:
            return existing
        code = generate_referral_code(uid)
        _client().table("profiles").update({"referral_code": code}).eq("id", uid).execute()
        return code
    except Exception:  # noqa: BLE001
        logger.exception("[REFERRAL] ensure_referral_code failed user=%s", uid[:8])
        return generate_referral_code(uid)


def find_referrer_by_code(code: str) -> dict[str, Any] | None:
    normalized = normalize_referral_code(code)
    if not normalized:
        return None
    try:
        result = (
            _client()
            .table("profiles")
            .select("id, full_name, email, referral_code")
            .eq("referral_code", normalized)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        logger.warning("[REFERRAL] find_referrer_by_code failed")
        return None


def claim_referral(referred_id: str, code: str) -> dict[str, Any]:
    """Vincula al usuario autenticado con el socio dueño del Referral ID."""
    uid = (referred_id or "").strip()
    normalized = normalize_referral_code(code)
    if not uid or not normalized:
        return {"ok": False, "reason": "invalid"}
    referrer = find_referrer_by_code(normalized)
    if not referrer or not referrer.get("id"):
        return {"ok": False, "reason": "unknown_code"}
    referrer_id = str(referrer["id"])
    if referrer_id == uid:
        return {"ok": False, "reason": "self"}
    try:
        existing = (
            _client()
            .table("users_referrals")
            .select("id, referrer_id, referral_code")
            .eq("referred_id", uid)
            .limit(1)
            .execute()
        )
        rows = existing.data or []
        already = bool(rows)
        if not already:
            _client().table("users_referrals").insert(
                {
                    "referrer_id": referrer_id,
                    "referred_id": uid,
                    "referral_code": normalized,
                }
            ).execute()
            logger.info(
                "[REFERRAL] claimed referrer=%s referred=%s code=%s",
                referrer_id[:8],
                uid[:8],
                normalized,
            )
        snapshot_structure_partner(referrer_id, uid, normalized)
        return {
            "ok": True,
            "already": already,
            "referrer_id": referrer_id,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("[REFERRAL] claim failed user=%s", uid[:8])
        return {"ok": False, "reason": "db_error", "error": str(exc)[:160]}


def _profile_row(user_id: str, columns: str = "id, email, full_name, referral_code, pm_partner_id") -> dict[str, Any]:
    uid = (user_id or "").strip()
    if not uid:
        return {}
    try:
        row = (
            _client()
            .table("profiles")
            .select(columns)
            .eq("id", uid)
            .limit(1)
            .execute()
        )
        return (row.data or [None])[0] or {}
    except Exception:  # noqa: BLE001
        if "pm_partner_id" in columns:
            return _profile_row(
                uid, columns.replace(", pm_partner_id", "").replace("pm_partner_id, ", "")
            )
        return {}


def find_profile_by_email(email: str) -> dict[str, Any] | None:
    email_n = (email or "").strip().lower()
    if not EMAIL_RE.match(email_n):
        return None
    try:
        row = (
            _client()
            .table("profiles")
            .select("id, email, full_name, referral_code")
            .eq("email", email_n)
            .limit(1)
            .execute()
        )
        rows = row.data or []
        return rows[0] if rows else None
    except Exception:  # noqa: BLE001
        logger.warning("[REFERRAL] find_profile_by_email failed")
        return None


def save_pm_partner_id(user_id: str, pm_partner_id: str) -> bool:
    uid = (user_id or "").strip()
    pid = normalize_pm_partner_id(pm_partner_id)
    if not uid or not pid:
        return False
    try:
        _client().table("profiles").update({"pm_partner_id": pid}).eq("id", uid).execute()
        return True
    except Exception:  # noqa: BLE001
        logger.warning("[REFERRAL] save pm_partner_id failed user=%s", uid[:8])
        return False


def snapshot_structure_partner(
    sponsor_id: str,
    referred_id: str,
    sponsor_ced_id: str,
    *,
    full_name: str = "",
    email: str = "",
    pm_partner_id: str = "",
) -> bool:
    """Guarda nombre, correo e ID de socio PM en la estructura del patrocinador."""
    sid = (sponsor_id or "").strip()
    uid = (referred_id or "").strip()
    if not sid:
        return False
    profile = _profile_row(uid) if uid else {}
    name = (full_name or str(profile.get("full_name") or "")).strip()
    mail = (email or str(profile.get("email") or "")).strip().lower()
    partner_pm = normalize_pm_partner_id(pm_partner_id) or normalize_pm_partner_id(
        str(profile.get("pm_partner_id") or "")
    )
    if not mail or not EMAIL_RE.match(mail):
        return False
    if not name:
        name = mail.split("@", 1)[0]
    payload = {
        "sponsor_id": sid,
        "full_name": name[:160],
        "email": mail,
        "sponsor_ced_id": normalize_referral_code(sponsor_ced_id) or "",
        "user_id": uid or None,
        "partner_ced_id": partner_pm or None,
        "updated_at": _now().isoformat(),
    }
    try:
        _client().table("pm_structure_partners").upsert(
            payload,
            on_conflict="sponsor_id,email",
        ).execute()
        return True
    except Exception:  # noqa: BLE001
        logger.warning("[REFERRAL] snapshot partner skipped sponsor=%s", sid[:8])
        return False


def complete_pm_profile(
    user_id: str,
    *,
    full_name: str,
    pm_partner_id: str = "",
    sponsor_ced_id: str = "",
) -> dict[str, Any]:
    """Onboarding Estructura PM: nombre completo + ID de socio PM."""
    uid = (user_id or "").strip()
    name = " ".join((full_name or "").split()).strip()
    if not uid:
        return {"ok": False, "reason": "invalid"}
    if len(name) < 3:
        return {"ok": False, "reason": "invalid_name"}
    try:
        _client().table("profiles").update({"full_name": name[:160]}).eq("id", uid).execute()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[REFERRAL] complete profile failed user=%s", uid[:8])
        return {"ok": False, "reason": "db_error", "error": str(exc)[:160]}

    pid = normalize_pm_partner_id(pm_partner_id)
    if pid:
        save_pm_partner_id(uid, pid)

    code = (sponsor_ced_id or "").strip()
    if code:
        claimed = claim_referral(uid, code)
        if not claimed.get("ok"):
            return claimed

    return {"ok": True, **list_my_team(uid)}


def add_structure_partner(
    sponsor_id: str,
    *,
    full_name: str,
    email: str,
    pm_partner_id: str = "",
    ced_id: str = "",
) -> dict[str, Any]:
    """Alta de socio: correo, nombre completo e ID de socio PM International."""
    sid = (sponsor_id or "").strip()
    name = " ".join((full_name or "").split()).strip()
    mail = (email or "").strip().lower()
    partner_pm = normalize_pm_partner_id(pm_partner_id or ced_id)
    if not sid:
        return {"ok": False, "reason": "invalid"}
    if len(name) < 3:
        return {"ok": False, "reason": "invalid_name"}
    if not EMAIL_RE.match(mail):
        return {"ok": False, "reason": "invalid_email"}
    if not partner_pm:
        return {"ok": False, "reason": "invalid_pm_partner_id"}

    my_code = ensure_referral_code(sid)

    existing_user = find_profile_by_email(mail)
    referred_id = str((existing_user or {}).get("id") or "")
    if referred_id == sid:
        return {"ok": False, "reason": "self"}

    if referred_id:
        if my_code:
            try:
                claim_referral(referred_id, my_code)
            except Exception:  # noqa: BLE001
                pass
        if existing_user and not str(existing_user.get("full_name") or "").strip():
            try:
                _client().table("profiles").update({"full_name": name[:160]}).eq(
                    "id", referred_id
                ).execute()
            except Exception:  # noqa: BLE001
                pass
        save_pm_partner_id(referred_id, partner_pm)
        snapshot_structure_partner(
            sid,
            referred_id,
            my_code,
            full_name=name,
            email=mail,
            pm_partner_id=partner_pm,
        )
    else:
        saved = snapshot_structure_partner(
            sid,
            "",
            my_code,
            full_name=name,
            email=mail,
            pm_partner_id=partner_pm,
        )
        if not saved:
            return {"ok": False, "reason": "db_error"}

    return {"ok": True, **list_my_team(sid)}


def note_activity(
    user_id: str,
    kind: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    uid = (user_id or "").strip()
    if not uid or kind not in ACTIVITY_KINDS:
        return
    try:
        _client().table("referral_activity_events").insert(
            {
                "user_id": uid,
                "kind": kind,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception:  # noqa: BLE001
        logger.debug("[REFERRAL] note_activity skipped kind=%s", kind)


def note_sales_chat_if_relevant(user_id: str, text: str) -> None:
    if is_relevant_sales_chat(text):
        note_activity(user_id, "chat_sales")


def _latest(rows: list[dict[str, Any]], field: str = "created_at") -> str | None:
    best: datetime | None = None
    raw_best: str | None = None
    for row in rows:
        parsed = _parse_dt(row.get(field) or row.get("updated_at"))
        if parsed and (best is None or parsed > best):
            best = parsed
            raw_best = str(row.get(field) or row.get("updated_at") or "")
    return raw_best


def _has_since(iso: str | None, days: int) -> bool:
    dt = _parse_dt(iso)
    if not dt:
        return False
    return dt >= _now() - timedelta(days=days)


def _guest_activity(user_id: str) -> dict[str, Any]:
    """Señales de uso real para vender — no logins ni chat genérico."""
    since14 = _iso_since(LOOKBACK_DAYS)
    voice_minutes = 0.0
    voice_last = None
    try:
        usage = (
            _client()
            .table("usage_logs")
            .select("minutes_consumed, created_at")
            .eq("user_id", user_id)
            .gte("created_at", since14)
            .limit(200)
            .execute()
        )
        urows = usage.data or []
        voice_minutes = round(
            sum(float(r.get("minutes_consumed") or 0) for r in urows), 2
        )
        voice_last = _latest(urows)
    except Exception:  # noqa: BLE001
        urows = []

    pm_questions = 0
    try:
        eng = (
            _client()
            .table("ced_fitline_engagement")
            .select("question_count, updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        erows = eng.data or []
        if erows:
            pm_questions = int(erows[0].get("question_count") or 0)
    except Exception:  # noqa: BLE001
        erows = []

    events: list[dict[str, Any]] = []
    try:
        ev = (
            _client()
            .table("referral_activity_events")
            .select("kind, created_at")
            .eq("user_id", user_id)
            .gte("created_at", since14)
            .limit(200)
            .execute()
        )
        events = ev.data or []
    except Exception:  # noqa: BLE001
        events = []

    def _event_last(kind: str) -> str | None:
        return _latest([e for e in events if e.get("kind") == kind])

    chat_last = _event_last("chat_sales")
    finance_event_last = _event_last("finance")
    opps_event_last = _event_last("opps")
    sponsor_event_last = _event_last("sponsor")
    voice_pm_event = _event_last("voice_pm")

    finance_last = finance_event_last
    try:
        tx = (
            _client()
            .table("finance_transactions")
            .select("created_at")
            .eq("user_id", user_id)
            .gte("created_at", since14)
            .limit(20)
            .execute()
        )
        finance_last = _latest(tx.data or []) or finance_last
    except Exception:  # noqa: BLE001
        pass
    try:
        plans = (
            _client()
            .table("fitline_action_plans")
            .select("updated_at, created_at")
            .eq("user_id", user_id)
            .limit(5)
            .execute()
        )
        finance_last = _latest(plans.data or [], "updated_at") or finance_last
    except Exception:  # noqa: BLE001
        pass

    opps_last = opps_event_last
    try:
        mods = (
            _client()
            .table("module_usage")
            .select("created_at")
            .eq("user_id", user_id)
            .eq("module", "opportunities")
            .gte("created_at", since14)
            .limit(20)
            .execute()
        )
        opps_last = _latest(mods.data or []) or opps_last
    except Exception:  # noqa: BLE001
        pass

    own_sponsor = False
    try:
        prof = (
            _client()
            .table("profiles")
            .select("fitline_sponsor_url")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        prow = (prof.data or [None])[0] or {}
        own_sponsor = bool(str(prow.get("fitline_sponsor_url") or "").strip())
    except Exception:  # noqa: BLE001
        own_sponsor = False

    voice_used = voice_minutes > 0.05
    voice_pm = voice_used and (pm_questions > 0 or bool(voice_pm_event))
    chat_sales = bool(chat_last) or pm_questions > 0
    finance_used = bool(finance_last)
    opps_used = bool(opps_last) or own_sponsor or bool(sponsor_event_last)

    last_candidates = [
        voice_last,
        voice_pm_event,
        chat_last,
        finance_last,
        opps_last,
        sponsor_event_last,
        (erows[0].get("updated_at") if erows else None),
    ]
    last_relevant = None
    best_dt = None
    for cand in last_candidates:
        parsed = _parse_dt(cand)
        if parsed and (best_dt is None or parsed > best_dt):
            best_dt = parsed
            last_relevant = cand

    any_relevant = voice_used or chat_sales or finance_used or opps_used
    if any_relevant and _has_since(last_relevant, ACTIVE_DAYS):
        status = "active"
    elif any_relevant:
        status = "idle"
    else:
        status = "unused"

    return {
        "status": status,
        "last_relevant_at": last_relevant,
        "signals": {
            "voice": {
                "used": voice_used,
                "pm_context": voice_pm,
                "minutes_14d": voice_minutes,
            },
            "chat_sales": {"used": chat_sales, "pm_questions": pm_questions},
            "finance": {"used": finance_used},
            "opps": {
                "used": opps_used,
                "viewed_ficha": bool(opps_last),
                "own_sponsor": own_sponsor,
            },
        },
    }


def invite_url_for_code(code: str) -> str:
    from app.config import get_settings

    base = (get_settings().web_public_url or "https://ced-castillo.com").rstrip("/")
    return f"{base}/signup?ref={code}"


def list_my_team(referrer_id: str) -> dict[str, Any]:
    uid = (referrer_id or "").strip()
    code = ensure_referral_code(uid)
    me_profile = _profile_row(uid)
    me_name = str(me_profile.get("full_name") or "").strip()
    me_email = str(me_profile.get("email") or "").strip()
    guests: list[dict[str, Any]] = []
    try:
        links = (
            _client()
            .table("users_referrals")
            .select("referred_id, referral_code, created_at")
            .eq("referrer_id", uid)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        rows = links.data or []
    except Exception:  # noqa: BLE001
        logger.exception("[REFERRAL] list links failed user=%s", uid[:8])
        rows = []

    ids = [str(r.get("referred_id") or "") for r in rows if r.get("referred_id")]
    profiles_by_id: dict[str, dict[str, Any]] = {}
    if ids:
        try:
            profs = (
                _client()
                .table("profiles")
                .select("id, full_name, email, created_at, referral_code, pm_partner_id")
                .in_("id", ids)
                .execute()
            )
            for p in profs.data or []:
                profiles_by_id[str(p.get("id"))] = p
        except Exception:  # noqa: BLE001
            try:
                profs = (
                    _client()
                    .table("profiles")
                    .select("id, full_name, email, created_at, referral_code")
                    .in_("id", ids)
                    .execute()
                )
                for p in profs.data or []:
                    profiles_by_id[str(p.get("id"))] = p
            except Exception:  # noqa: BLE001
                logger.warning("[REFERRAL] profiles batch failed")

    partners: list[dict[str, Any]] = []
    try:
        prow = (
            _client()
            .table("pm_structure_partners")
            .select(
                "id, full_name, email, sponsor_ced_id, user_id, partner_ced_id, created_at"
            )
            .eq("sponsor_id", uid)
            .order("created_at", desc=True)
            .limit(200)
            .execute()
        )
        partners = prow.data or []
    except Exception:  # noqa: BLE001
        partners = []

    seen_emails: set[str] = set()
    seen_users: set[str] = set()
    active = idle = unused = pending = 0

    def _append_guest(
        *,
        gid: str,
        full_name: str,
        email: str,
        ced_id: str,
        joined_at: object,
        registered: bool,
    ) -> None:
        nonlocal active, idle, unused, pending
        mail = (email or "").strip().lower()
        if mail:
            if mail in seen_emails:
                return
            seen_emails.add(mail)
        if gid:
            if gid in seen_users:
                return
            seen_users.add(gid)
        if registered and gid:
            activity = _guest_activity(gid)
            st = activity["status"]
            if st == "active":
                active += 1
            elif st == "idle":
                idle += 1
            else:
                unused += 1
            signals = activity.get("signals")
            last_relevant = activity.get("last_relevant_at")
        else:
            st = "pending"
            pending += 1
            signals = {
                "voice": {"used": False, "pm_context": False, "minutes_14d": 0},
                "chat_sales": {"used": False, "pm_questions": 0},
                "finance": {"used": False},
                "opps": {"used": False, "viewed_ficha": False, "own_sponsor": False},
            }
            last_relevant = None
        guests.append(
            {
                "id": gid or mail or str(joined_at or ""),
                "display_name": display_name_from_profile(
                    {"full_name": full_name, "email": email}
                ),
                "full_name": (full_name or "").strip() or display_name_from_profile(
                    {"email": email}
                ),
                "email": mail,
                "ced_id": ced_id or "",
                "joined_at": joined_at,
                "status": st,
                "last_relevant_at": last_relevant,
                "signals": signals,
            }
        )

    for row in rows:
        gid = str(row.get("referred_id") or "")
        if not gid:
            continue
        prof = profiles_by_id.get(gid) or {}
        partner_pm = normalize_pm_partner_id(str(prof.get("pm_partner_id") or ""))
        _append_guest(
            gid=gid,
            full_name=str(prof.get("full_name") or ""),
            email=str(prof.get("email") or ""),
            ced_id=partner_pm,
            joined_at=row.get("created_at"),
            registered=True,
        )

    for partner in partners:
        gid = str(partner.get("user_id") or "")
        mail = str(partner.get("email") or "").strip().lower()
        if gid and gid in seen_users:
            continue
        if mail and mail in seen_emails:
            continue
        _append_guest(
            gid=gid,
            full_name=str(partner.get("full_name") or ""),
            email=mail,
            ced_id=normalize_pm_partner_id(str(partner.get("partner_ced_id") or ""))
            or "",
            joined_at=partner.get("created_at"),
            registered=bool(gid),
        )

    me_pm = normalize_pm_partner_id(str(me_profile.get("pm_partner_id") or ""))
    return {
        "ok": True,
        "referral_code": code,
        "invite_url": invite_url_for_code(code) if code else "",
        "me": {
            "email": me_email,
            "full_name": me_name,
            "referral_code": code,
            "pm_partner_id": me_pm,
            "needs_onboarding": len(me_name) < 3,
        },
        "counts": {
            "total": len(guests),
            "active": active,
            "idle": idle,
            "unused": unused,
            "pending": pending,
        },
        "guests": guests,
        "criteria": {
            "voice": "Asistente de voz (minutos reales; PM si hay preguntas FitLine)",
            "chat_sales": "Chat de venta/prospección o preguntas PM/FitLine",
            "finance": "Módulo Finanzas o plan de acción de franquicia",
            "opps": "Ficha de Oportunidades o enlace propio de patrocinio",
        },
    }
