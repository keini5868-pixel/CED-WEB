# Opportunities Module (Oportunidades) — pilot

Isolated like Viability / Tendencias: rail module only, no public chat, no voice, no Q&A in v1.

| Layer | Gate |
|--------|------|
| Web UI | `?opportunitiesModule=pilot` (shell + **Oportunidades** / OPPS) |
| HTTP API | Header `X-CED-Opportunities-Pilot: 1` **required** (404 without it) |
| Env | `OPPORTUNITIES_MODULE_PILOT` (set `false` to disable) |
| Sponsor CTA | `OPPORTUNITIES_FITLINE_SPONSOR_URL` (optional until configured) |
| Voice / chat | Not wired |
| Q&A | Not in v1 |

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

1. Open CED with `?opportunitiesModule=pilot`.
2. Left rail → **OPPS** → open FitLine ficha.
3. Closing the drawer discards state.

### Key paths

- Content: `OpportunitiesModuleContent` in `OpportunitiesPilotPanel.tsx`
- API: `apps/api/app/services/opportunities_pilot/` + `routers/opportunities_pilot.py`
- Registry: `apps/web/src/modules/registry.ts`
