"""Constantes cerradas — anti-alucinación del módulo Automatización."""

from __future__ import annotations

CHANNELS = frozenset({"instagram", "facebook", "whatsapp"})

TRIGGER_TYPES = frozenset(
    {
        "dm_new",
        "dm_keyword",
        "comment_keyword",
        "comment_any",
        "lead_form",
        "wa_first_contact",
        "wa_outside_hours",
        "wa_inactivity_followup",
        "wa_fitline_link_after_questions",
        "wa_hot_lead_notify",
        "nurture_day",
    }
)

ACTION_TYPES = frozenset(
    {
        "reply_text",
        "reply_whatsapp_link",
        "notify_owner",
        "tag_lead",
        "nurture_step",
        "ced_dynamic_reply",
    }
)

# Tarjetas curadas iniciales (WhatsApp) + captura IG/FB.
CURATED_CARDS: list[dict[str, object]] = [
    {
        "card_key": "ig_comment_keyword",
        "channel": "instagram",
        "trigger_type": "comment_keyword",
        "name": "Comentario con palabra clave (Instagram)",
        "description": (
            "Cuando alguien comenta una palabra clave en tus posts o reels, "
            "CED responde y le pasa el enlace de WhatsApp."
        ),
        "default_trigger": {"keywords": ["info", "quiero", "precio"]},
        "default_action": {
            "type": "reply_whatsapp_link",
            "reply_text": (
                "¡Hola! Te comparto más información por WhatsApp: {whatsapp_link}"
            ),
            "wa_prefill": "Hola, vi tu contenido en Instagram y quiero más info",
        },
    },
    {
        "card_key": "ig_dm_new",
        "channel": "instagram",
        "trigger_type": "dm_new",
        "name": "Mensaje directo nuevo (Instagram)",
        "description": (
            "Responde automáticamente a un DM nuevo y ofrece continuar por WhatsApp."
        ),
        "default_trigger": {},
        "default_action": {
            "type": "reply_whatsapp_link",
            "reply_text": (
                "Gracias por escribirme. Sigamos por WhatsApp para atenderte mejor: "
                "{whatsapp_link}"
            ),
            "wa_prefill": "Hola, te escribí por Instagram",
        },
    },
    {
        "card_key": "fb_comment_keyword",
        "channel": "facebook",
        "trigger_type": "comment_keyword",
        "name": "Comentario con palabra clave (Facebook)",
        "description": (
            "Responde a comentarios con palabra clave en publicaciones o anuncios "
            "y deriva a WhatsApp."
        ),
        "default_trigger": {"keywords": ["info", "interesado", "precio"]},
        "default_action": {
            "type": "reply_whatsapp_link",
            "reply_text": (
                "¡Gracias por tu interés! Continúa por WhatsApp: {whatsapp_link}"
            ),
            "wa_prefill": "Hola, comenté en Facebook y quiero más información",
        },
    },
    {
        "card_key": "fb_dm_new",
        "channel": "facebook",
        "trigger_type": "dm_new",
        "name": "Messenger nuevo (Facebook)",
        "description": "Responde a un mensaje nuevo en Messenger y deriva a WhatsApp.",
        "default_trigger": {},
        "default_action": {
            "type": "reply_whatsapp_link",
            "reply_text": (
                "Hola, gracias por escribir. Te atiendo más rápido por WhatsApp: "
                "{whatsapp_link}"
            ),
            "wa_prefill": "Hola, te contacté por Facebook Messenger",
        },
    },
    {
        "card_key": "wa_welcome",
        "channel": "whatsapp",
        "trigger_type": "wa_first_contact",
        "name": "Bienvenida en WhatsApp",
        "description": "Primer mensaje automático al contactar por WhatsApp.",
        "default_trigger": {},
        "default_action": {
            "type": "reply_text",
            "reply_text": (
                "¡Bienvenido! Soy el asistente de CED. ¿En qué puedo ayudarte hoy?"
            ),
        },
    },
    {
        "card_key": "wa_outside_hours",
        "channel": "whatsapp",
        "trigger_type": "wa_outside_hours",
        "name": "Fuera de horario",
        "description": "Respuesta automática cuando escriben fuera de tu horario.",
        "default_trigger": {"hours": {"start": "09:00", "end": "18:00", "tz": "America/Caracas"}},
        "default_action": {
            "type": "reply_text",
            "reply_text": (
                "Gracias por escribir. Ahora estamos fuera de horario; "
                "te responderemos en cuanto estemos disponibles."
            ),
        },
    },
    {
        "card_key": "wa_followup_inactive",
        "channel": "whatsapp",
        "trigger_type": "wa_inactivity_followup",
        "name": "Seguimiento por inactividad",
        "description": "Recontacta a quien no responde después de X días.",
        "default_trigger": {"idle_days": 3},
        "default_action": {
            "type": "reply_text",
            "reply_text": (
                "Hola, ¿seguimos en contacto? Quedo atento si tienes alguna duda."
            ),
        },
    },
    {
        "card_key": "wa_fitline_after_questions",
        "channel": "whatsapp",
        "trigger_type": "wa_fitline_link_after_questions",
        "name": "Enlace FitLine / OPPS",
        "description": (
            "Tras 2–3 preguntas sobre PM International / FitLine, envía el enlace de afiliación."
        ),
        "default_trigger": {"min_questions": 2, "topics": ["fitline", "pm international", "pm"]},
        "default_action": {
            "type": "reply_text",
            "reply_text": (
                "Con gusto te comparto el enlace para conocer FitLine / PM International: "
                "{fitline_link}"
            ),
        },
    },
    {
        "card_key": "wa_hot_lead",
        "channel": "whatsapp",
        "trigger_type": "wa_hot_lead_notify",
        "name": "Aviso de lead caliente",
        "description": (
            "Te notifica cuando el prospecto usa palabras de intención de compra."
        ),
        "default_trigger": {
            "keywords": ["comprar", "precio", "quiero empezar", "inscribirme", "pedido"],
        },
        "default_action": {
            "type": "notify_owner",
            "notify_text": "Lead caliente detectado en WhatsApp ({contact_id}).",
            "tag": "caliente",
        },
    },
]

NURTURE_DEFAULT_DAYS: list[dict[str, object]] = [
    {"day": 1, "label": "Bienvenida + valor", "reply_text": "Día 1: bienvenida y propuesta de valor."},
    {"day": 2, "label": "Educación / testimonios", "reply_text": "Día 2: contenido educativo o testimonio."},
    {"day": 3, "label": "Oferta / CTA", "reply_text": "Día 3: oferta clara y llamado a la acción."},
    {"day": 5, "label": "Follow-up", "reply_text": "Día 5: seguimiento si no hubo respuesta."},
    {"day": 7, "label": "Cierre o reactivación", "reply_text": "Día 7: cierre o reactivación suave."},
]
