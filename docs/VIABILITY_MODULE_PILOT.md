# Análisis de Producto — production

Isolated rail module: product/service market viability analysis.
Graduated from pilot — visible for logged-in users unless kill-switched off.

| Layer | Gate |
|--------|------|
| Web UI | On by default (`NEXT_PUBLIC_VIABILITY_MODULE_ENABLED=false` to hide; `?viabilityModule=off` local escape) |
| HTTP API | Auth required (`require_user_id`); kill-switch `VIABILITY_MODULE_ENABLED=false` → 404 |
| Voice | Retell tool `analyze_product_viability` when kill-switch is ON |

### How to test

1. Open CED logged in (no query flag needed).
2. Left rail → **Análisis de Producto** → describe product or upload flyer.
3. Closing the drawer discards state.
4. Emergency off: `VIABILITY_MODULE_ENABLED=false` (API) and/or `NEXT_PUBLIC_VIABILITY_MODULE_ENABLED=false` (web).

### Key paths

- Content: `ViabilityModuleContent` in `ViabilityPilotPanel.tsx`
- API: `apps/api/app/services/viability_pilot/` + `routers/viability_pilot.py`
- Registry: `apps/web/src/modules/registry.ts`
- Kill-switch: `VIABILITY_MODULE_ENABLED`
