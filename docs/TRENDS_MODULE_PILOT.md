# Análisis de Tendencia — production

Isolated rail module: industry trends analysis.
Graduated from pilot — visible for logged-in users unless kill-switched off.

| Layer | Gate |
|--------|------|
| Web UI | On by default (`NEXT_PUBLIC_TRENDS_MODULE_ENABLED=false` to hide; `?trendsModule=off` local escape) |
| HTTP API | Auth required (`require_user_id`); kill-switch `TRENDS_MODULE_ENABLED=false` → 404 |
| Voice / chat | Not wired |

### How to test

1. Open CED logged in (no query flag needed).
2. Left rail → **Análisis de Tendencia** → describe industry/rubro.
3. Closing the drawer discards state.
4. Emergency off: `TRENDS_MODULE_ENABLED=false` (API) and/or `NEXT_PUBLIC_TRENDS_MODULE_ENABLED=false` (web).

### Key paths

- Content: `TrendsModuleContent` in `TrendsPilotPanel.tsx`
- API: `apps/api/app/services/trends_pilot/` + `routers/trends_pilot.py`
- Registry: `apps/web/src/modules/registry.ts`
- Kill-switch: `TRENDS_MODULE_ENABLED`
