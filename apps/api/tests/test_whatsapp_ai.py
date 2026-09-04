from app.services.whatsapp_ai import build_whatsapp_user_content


def test_goal_and_cta_are_in_prompt():
    prompt = build_whatsapp_user_content(
        inbound_text="Hola, vi tu anuncio",
        goal="Invitar al grupo de WhatsApp de onboarding",
        cta_url="https://chat.whatsapp.com/ejemplo",
        cta_label="Grupo onboarding",
    )
    assert "Invitar al grupo de WhatsApp de onboarding" in prompt
    assert "https://chat.whatsapp.com/ejemplo" in prompt
    assert "Hola, vi tu anuncio" in prompt
    assert "No inventes precios" in prompt


def test_mission_overlay_in_prompt():
    prompt = build_whatsapp_user_content(
        inbound_text="listo, cómo pago",
        goal="Agendar llamada",
        mission="ADN del prospecto: Decidido.",
    )
    assert "ADN del prospecto: Decidido." in prompt
    assert "Directriz de misión" in prompt


def test_empty_goal_still_asks_for_next_step():
    prompt = build_whatsapp_user_content(inbound_text="info")
    assert "aún no fijó una directriz" in prompt
    assert "info" in prompt
