# Product/Service Viability Module + Module Shell

## Phase 1 — Viability analysis (pilot-only)

| Layer | Gate |
|--------|------|
| Web UI | `?viabilityModule=pilot` (shows lateral shell + Viability icon) |
| HTTP API | Header `X-CED-Viability-Pilot: 1` **required** (404 without it) |
| Env | `VIABILITY_MODULE_PILOT` (set `false` to disable API) |
| Voice | `analyze_product_viability` on Retell **native pilot** only |
| Public chat | Not wired into production text chat |

### How to test

1. Open CED with `?viabilityModule=pilot` (optional `?voicePilot=native` for voice).
2. Left rail → **VIABLE** → drawer with text/image analysis.
3. Voice (native pilot): *«Analiza la viabilidad de mi…»*.
4. Closing the drawer discards in-progress state.

---

## Phase 2 — Lateral module shell (signed off + implemented)

### Decisions (2026-07-22)

| Topic | Decision |
|--------|----------|
| Placement | **Lateral drawer / left rail** (not top bar) |
| State on close | **Discard** (unmount). Persistence later if needed |
| Voice for future modules | **Pilot-only until each module graduates** (same discipline as voice system) |

### Adding a module

1. Implement a self-contained panel exporting `ComponentType<ModulePanelProps>`.
2. Append one entry to `apps/web/src/modules/registry.ts` (id, name, icon, `isPilotEnabled`, `load`).
3. Do **not** edit `CedVoiceControls`, `text_chat`, or shared voice session for the new module.
4. Keep voice tools on native/staging pilot until graduation.

### Key paths

- Shell: `apps/web/src/components/modules/ModuleShell.tsx`
- Registry: `apps/web/src/modules/registry.ts`
- Viability content: `ViabilityModuleContent` in `ViabilityPilotPanel.tsx`
- API: `apps/api/app/services/viability_pilot/`
