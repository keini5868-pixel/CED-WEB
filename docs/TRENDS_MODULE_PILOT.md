# Industry Trends Module (Tendencias) — pilot

Isolated like Viability: rail module only, no public chat, no voice (yet).

| Layer | Gate |
|--------|------|
| Web UI | `?trendsModule=pilot` (shell + **Tendencias** / TRENDS) |
| HTTP API | Header `X-CED-Trends-Pilot: 1` **required** (404 without it) |
| Env | `TRENDS_MODULE_PILOT` (set `false` to disable API) |
| Voice | Not wired |
| Public chat | Not wired |

### Product decisions

| Topic | Decision |
|--------|----------|
| Visible name | **Tendencias** (id interno `trends`) |
| Región | Optional field (same as VIABLE) |
| Outlook ~6 months | Always shown; if no search forecast → `model_reasoning` + data gap (do not omit) |

### How to test

1. Open CED with `?trendsModule=pilot` (can combine with `?viabilityModule=pilot`).
2. Left rail → **TRENDS** → describe rubro; optional region → Analizar.
3. Closing the drawer discards state (shell unmount).

### Key paths

- Content: `TrendsModuleContent` in `TrendsPilotPanel.tsx`
- API: `apps/api/app/services/trends_pilot/` + `routers/trends_pilot.py`
- Registry: `apps/web/src/modules/registry.ts`
