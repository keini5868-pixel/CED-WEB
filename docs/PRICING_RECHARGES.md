# Modelo de precios — CED Élite (producto único)

## Suscripción

| Fase | Cupo | Precio/mes | Notas |
|------|------|------------|-------|
| **Founding** | 1–50 | **$149** | Precio bloqueado de por vida si mantiene suscripción activa |
| **Launch** | 51+ | **$249** | Mismo producto, mismas funciones |

**Trial:** 7 días gratis, sin tarjeta.

**Producto incluye:** 120 min/día Gemini Live (audio+video), Claude texto ilimitado, 100 imágenes IA/mes, ElevenLabs, Whisper, memoria/carpetas/PDFs ilimitados, HUD SSE, PWA, soporte prioritario Keini.

---

## Recargas flexibles (Gemini Live extra)

Cuando el usuario agota sus **120 min/día**, puede comprar saldo adicional.

| Regla | Valor |
|-------|-------|
| Margen Keini | **40%** del monto pagado |
| Saldo de uso cliente | **60%** del monto pagado |
| Costo Gemini referencia | **$1.50 / hora** |
| Mínimo / máximo | **$5 – $500** |
| Botones rápidos | $10, $25, $50, $100 |
| Caducidad del saldo | **Nunca expira** |

### Fórmula

```
saldo_uso_usd = monto_pagado × 0.60
margen_keini = monto_pagado × 0.40
horas_extra = saldo_uso_usd / 1.50
```

### Ejemplos

| Paga | Saldo uso | Horas ~extra | Margen Keini |
|------|-----------|--------------|--------------|
| $10 | $6 | 4 h | $4 |
| $25 | $15 | 10 h | $10 |
| $50 | $30 | 20 h | $20 |
| $100 | $60 | 40 h | $40 |

### UI

- **80%** del límite diario: warning amarillo en HUD + CTA recarga
- **100%**: modal bloquea Gemini Live hasta recargar o esperar reset 00:00 (timezone usuario)

### API

- `GET /v1/meta` — incluye `recharge.example_quotes`
- `GET /v1/recharge/quote?amount_usd=25` — cotización en vivo

---

## Paquetes fijos eliminados

Los packs Booster / Power / Mega ($10/$20/$50 fijos) fueron **reemplazados** por monto flexible.
