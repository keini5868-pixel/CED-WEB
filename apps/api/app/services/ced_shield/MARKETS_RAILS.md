# CED — Mesa | Midnight (cimientos, no shipping)

**Cuándo construir el cajón:** después de Wave 2 / jueces. **Ahora:** spec + catálogo.  
**Shield:** `CED_SHIELD_ENABLED=false`. No mezclar con Jarvis.

## Dos rieles (nunca un botón)

| | Mesa | Midnight |
|---|---|---|
| Qué | Spot Kraken **curado** | NIGHT, Lace, Compact / Shield |
| Privacidad | Ninguna. KYC. | ZK de **prueba de existencia**, no del order book |
| Copy | Identificado, no privado | Privacidad por prueba, no por el CEX |
| Techo | Lo que Kraken liste **en ese país** | Lo que exista on-chain en Midnight |

**Puente:** Mesa compra NIGHT → withdraw Kraken red **Cardano** (otra red = pérdida) → wallet → Lace. CED nombra los tres pasos.

## Catálogo Mesa v1

BTC, ETH, SOL, ADA, USDC, USDT, **NIGHT**, XRP, LINK, AVAX (pares USD; filtrar `country_code`).  
Fuente de verdad de tickers: API pública Kraken (`Assets` / `AssetPairs`). CED **filtra**; no muestra 600 pares.  
Fuera de v1: memes de cola, margin, futuros, xStocks.

Deber técnico (sin cliente aún): OAuth vs API keys (cuenta **del usuario**, CED no custodia); spot only; withdraw NIGHT = Cardano; eligibility por región.

## HUD (diseño, no UI)

Un control como **Chats** (barra o Sistema → Mercados). Overlay desplegable, no sidebar. Pestañas Mesa | Midnight. Estados: no conectado / Mesa KYC / Midnight kill-switch. Sin “próximamente trading” en prod.

## AKINDO

Submit ~27 Sep 2026. Demo `/shield` + este kill-switch. No DM Hoskinson. Fallo Midnight ≠ fallo voz.
