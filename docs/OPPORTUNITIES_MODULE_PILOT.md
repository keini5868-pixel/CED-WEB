# Opportunities Module (Oportunidades) — production

Isolated like Viability / Tendencias: rail module only, no public chat, no voice, no Q&A in v1.
Graduated from pilot — always visible for logged-in users unless kill-switched off.

| Layer | Gate |
|--------|------|
| Web UI | On by default for logged-in users (`NEXT_PUBLIC_OPPORTUNITIES_MODULE_ENABLED=false` to hide; `?opportunitiesModule=off` local escape) |
| HTTP API | Auth required (`require_user_id`); kill-switch `OPPORTUNITIES_MODULE_ENABLED=false` → 404 |
| Sponsor CTA | `OPPORTUNITIES_FITLINE_SPONSOR_URL` (optional until configured) |
| Voice / chat | Not wired |
| Q&A | Not in v1 |

Viability, Tendencias and Oportunidades are production modules (kill-switches default ON).

### Product decisions

| Topic | Decision |
|--------|----------|
| Visible name | **Oportunidades** (short `OPPS`) |
| Data | Hybrid curated + search |
| Scope v1 | List + reading card only |
| Coming soon | Not shown — only FitLine/PMI |
| Soft tone | No MLM/afiliados wording in sections 1–6 |
| Risks | Honest language (venta directa, comisiones por red, no garantizado) |
| Afiliación CTA | «Activar su negocio (paquete manager)» |

### How to test

1. Open CED logged in (no query flag needed).
2. Left rail → **OPPS** → open FitLine ficha.
3. Closing the drawer discards state.
4. Emergency off: set `OPPORTUNITIES_MODULE_ENABLED=false` (API) and/or `NEXT_PUBLIC_OPPORTUNITIES_MODULE_ENABLED=false` (web).

### Key paths

- Content: `OpportunitiesModuleContent` in `OpportunitiesPilotPanel.tsx`
- API: `apps/api/app/services/opportunities_pilot/` + `routers/opportunities_pilot.py`
- Registry: `apps/web/src/modules/registry.ts`
- Kill-switch: `OPPORTUNITIES_MODULE_ENABLED`
