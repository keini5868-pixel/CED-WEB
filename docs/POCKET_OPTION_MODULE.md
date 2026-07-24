# Pocket Option — demo trading (solo admin)

Módulo experimental aislado. **No** está en el rail de VIABLE/TRENDS/OPPS.
**No** aparece en planes, precios ni landing.

| Layer | Gate |
|--------|------|
| Kill-switch | `POCKET_OPTION_MODULE_ENABLED=false` (**default OFF**) |
| Auth | Solo `require_super_admin` / `SUPER_ADMIN_EMAILS` |
| UI | `/admin/pocket-option` (lectura) |
| SSID | `POCKET_OPTION_SSID` en Railway — nunca frontend |

## Demo obligatorio

1. Si el SSID declara `isDemo:0` → abortar.
2. Tras conectar, `client.is_demo()` debe ser `True` o se aborta.
3. Cada orden re-verifica demo.

## Estrategias

1. **BOS** (`POCKET_OPTION_STRATEGY_BOS_ENABLED`, default ON) — prioridad.
2. **Alternadas** (`POCKET_OPTION_STRATEGY_ALT_ENABLED`, default OFF) — experimental.

Ambas usan invalidación por **rango fijo** compartido. Expiry: 60s.

## Espaciado

Worker async en lifespan API. Intervalo: `POCKET_OPTION_INTERVAL_SECONDS` (default 300).

## Activar en Railway (API)

```
POCKET_OPTION_MODULE_ENABLED=true
POCKET_OPTION_SSID=42["auth",{"session":"...","isDemo":1,...}]
POCKET_OPTION_ASSET=EURUSD_otc
POCKET_OPTION_AMOUNT=1
POCKET_OPTION_INTERVAL_SECONDS=300
POCKET_OPTION_STRATEGY_BOS_ENABLED=true
POCKET_OPTION_STRATEGY_ALT_ENABLED=false
```

SSID: DevTools → Network → WS → mensaje completo `42["auth",{...}]` de **cuenta demo**.
