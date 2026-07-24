"""Diagnostico REAL: crea una cuenta nueva de verdad via Supabase Admin API y
revisa que fila de subscriptions/usage_limits quedo creada por el trigger
on_auth_user_created / handle_new_user(), y que el estado de voz calculado
por get_user_access / voice_access_state sea el trial esperado (5 min/dia)."""

from __future__ import annotations

import io
import json
import sys
import time
import uuid

sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main() -> None:
    from app.services import supabase_db
    from app.services.admin_users import get_user_access
    from app.services.voice_usage import voice_access_state

    client = supabase_db._client()
    test_email = f"ced-trial-probe-{uuid.uuid4().hex[:10]}@example.com"
    print(f"Creando usuario de prueba real: {test_email}")

    result = client.auth.admin.create_user(
        {
            "email": test_email,
            "password": "TestTrial#2026xyz",
            "email_confirm": True,
        }
    )
    user_id = result.user.id
    print(f"user_id creado: {user_id}")

    # Dar tiempo al trigger on_auth_user_created / handle_new_user()
    time.sleep(2)

    sub = supabase_db.get_subscription(user_id)
    print("\n=== Fila subscriptions creada por el trigger ===")
    print(json.dumps(sub, ensure_ascii=False, default=str, indent=2))

    limits_row = (
        client.table("usage_limits").select("*").eq("user_id", user_id).limit(1).execute()
    )
    print("\n=== Fila usage_limits creada por el trigger ===")
    print(json.dumps(limits_row.data, ensure_ascii=False, default=str, indent=2))

    profile = supabase_db.get_profile(user_id)
    print("\n=== Perfil creado ===")
    print(json.dumps(profile, ensure_ascii=False, default=str, indent=2))

    allowed, access_msg, plan_minutes = get_user_access(user_id)
    print(f"\nget_user_access -> allowed={allowed} msg={access_msg!r} plan_minutes={plan_minutes}")

    state = voice_access_state(user_id)
    print("\n=== voice_access_state (lo que ve el frontend/voz) ===")
    print(json.dumps(state, ensure_ascii=False, default=str, indent=2))

    print("\n=== VEREDICTO ===")
    if not sub:
        print("[BUG CONFIRMADO] No se creó ninguna fila en subscriptions para la cuenta nueva.")
    elif sub.get("status") != "trialing":
        print(f"[BUG CONFIRMADO] status={sub.get('status')!r} (esperado 'trialing')")
    elif not sub.get("trial_ends_at"):
        print("[BUG CONFIRMADO] trial_ends_at es NULL (esperado ahora+7 días)")
    elif state.get("blocked") and state.get("access_message") not in ("trial",):
        print(f"[BUG CONFIRMADO] voice_access_state bloquea voz: {state}")
    elif plan_minutes != 5:
        print(f"[POSIBLE BUG] plan_minutes={plan_minutes} (esperado 5 para trial)")
    else:
        print("[OK] Trial de 5 min/día se aplicó correctamente a la cuenta nueva.")

    # Limpieza: borrar el usuario de prueba.
    try:
        client.auth.admin.delete_user(user_id)
        print(f"\nUsuario de prueba {user_id} eliminado.")
    except Exception as exc:  # noqa: BLE001
        print(f"\n[WARN] No se pudo borrar el usuario de prueba: {exc}")


if __name__ == "__main__":
    main()
