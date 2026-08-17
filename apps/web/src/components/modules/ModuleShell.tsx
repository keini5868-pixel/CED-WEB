"use client";

import { Loader2, X } from "lucide-react";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { AnimatePresence, motion } from "framer-motion";

import { isModulesShellVisible } from "@/lib/pilot/modulesShell";
import { getModuleById, getVisibleModules } from "@/modules/registry";
import type { CedModuleRegistration, ModulePanelProps } from "@/modules/types";

type LoadedPanel = ComponentType<ModulePanelProps>;

/**
 * Lateral module shell (signed-off):
 * - Left rail of square icons
 * - Fullscreen panel per module (safe-area aware)
 * - State discarded on close (unmount)
 * - Does not touch main CED chat or voice session
 */
export function ModuleShell() {
  const [modules, setModules] = useState<CedModuleRegistration[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  /** Bumps on each open so reopen always starts clean. */
  const [openGeneration, setOpenGeneration] = useState(0);
  const [Panel, setPanel] = useState<LoadedPanel | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const visible = isModulesShellVisible() ? getVisibleModules() : [];
    setModules(visible);
  }, []);

  const active = useMemo(
    () => (activeId ? getModuleById(activeId) : undefined),
    [activeId],
  );

  const hasPilotModules = modules.some((m) => m.stage === "pilot");
  const railModules = modules.filter((m) => m.stage === "pilot");
  const activeIsPilot = active?.stage === "pilot";

  const closeModule = useCallback(() => {
    setActiveId(null);
    setPanel(null);
    setLoadError(null);
  }, []);

  const openModule = useCallback((id: string) => {
    setActiveId(id);
    setOpenGeneration((g) => g + 1);
    setPanel(null);
    setLoadError(null);
  }, []);

  useEffect(() => {
    const onOpen = (ev: Event) => {
      const detail = (ev as CustomEvent<{ module?: string }>).detail;
      const mod = detail?.module?.trim();
      if (!mod) return;
      if (getModuleById(mod)) openModule(mod);
    };
    window.addEventListener("ced-open-module", onOpen);
    return () => window.removeEventListener("ced-open-module", onOpen);
  }, [openModule]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const mod = url.searchParams.get("mod")?.trim();
    if (mod && getModuleById(mod)) {
      openModule(mod);
    }
    if (!mod) return;
    url.searchParams.delete("mod");
    const qs = url.searchParams.toString();
    window.history.replaceState(
      {},
      "",
      `${url.pathname}${qs ? `?${qs}` : ""}${url.hash}`,
    );
  }, [openModule]);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    const mod = getModuleById(activeId);
    if (!mod) return;
    void mod
      .load()
      .then((m) => {
        if (!cancelled) setPanel(() => m.default);
      })
      .catch(() => {
        if (!cancelled) setLoadError("No se pudo cargar el módulo.");
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, openGeneration]);

  useEffect(() => {
    if (!activeId) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [activeId]);

  return (
    <>
      {railModules.length > 0 ? (
        <aside
          className="pointer-events-auto fixed left-2 top-1/2 z-[70] flex -translate-y-1/2 flex-col gap-2 rounded-2xl ced-gold-outline bg-[#060b14]/95 p-2 shadow-xl backdrop-blur-md sm:left-3"
          aria-label="Módulos piloto CED"
        >
        {hasPilotModules ? (
          <div className="mb-0.5 px-0.5 text-center text-[8px] font-semibold uppercase tracking-wider text-amber-400/80">
            Piloto
          </div>
        ) : null}
        {railModules.map((m) => {
          const Icon = m.icon;
          const activeMod = activeId === m.id;
          return (
            <button
              key={m.id}
              type="button"
              title={m.name}
              onClick={() => {
                if (activeMod) closeModule();
                else openModule(m.id);
              }}
              className={`flex h-11 w-11 flex-col items-center justify-center rounded-xl ced-gold-outline transition ${
                activeMod
                  ? "bg-cyan-500/20 text-cyan-100"
                  : "bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              <Icon className="h-5 w-5" strokeWidth={1.75} />
              <span className="mt-0.5 text-[7px] font-semibold tracking-wide">
                {m.short}
              </span>
            </button>
          );
        })}
        </aside>
      ) : null}

      <AnimatePresence>
        {activeId && active ? (
          <motion.div
            key={`drawer-${activeId}-${openGeneration}`}
            role="dialog"
            aria-modal="true"
            aria-label={active.name}
            className="fixed inset-0 z-[200] flex flex-col bg-[#0a1220]"
            initial={{ opacity: 0.92, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            transition={{ type: "spring", stiffness: 380, damping: 34 }}
          >
            <header className="flex shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4 pb-3.5 pt-[max(2.75rem,env(safe-area-inset-top,0px))] sm:px-6 sm:pb-4 sm:pt-4">
              <div className="flex min-w-0 items-center gap-3">
                {(() => {
                  const ActiveIcon = active.icon;
                  return (
                    <ActiveIcon
                      className="h-5 w-5 shrink-0 text-cyan-400"
                      strokeWidth={1.75}
                    />
                  );
                })()}
                <div className="min-w-0">
                  <div className="truncate font-[family-name:var(--font-orbitron)] text-base font-semibold tracking-[0.04em] text-cyan-50 sm:text-lg">
                    {active.name}
                  </div>
                  <div
                    className={`mt-0.5 text-[11px] tracking-wide ${
                      activeIsPilot ? "text-amber-400/80" : "text-slate-500"
                    }`}
                  >
                    {activeIsPilot
                      ? "Piloto — se descarta al cerrar"
                      : "Se descarta al cerrar"}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={closeModule}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/5 text-slate-200 transition hover:border-cyan-400/50 hover:bg-cyan-500/15 hover:text-white"
                aria-label="Cerrar módulo"
                title="Cerrar"
              >
                <X className="h-5 w-5" strokeWidth={2} />
              </button>
            </header>

            <div className="flex min-h-0 flex-1 flex-col overflow-hidden pb-[env(safe-area-inset-bottom,0px)]">
              {loadError ? (
                <p className="p-5 text-sm text-red-400">{loadError}</p>
              ) : Panel ? (
                <Suspense
                  fallback={
                    <div className="flex flex-1 items-center justify-center gap-2 text-sm text-slate-400">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Cargando…
                    </div>
                  }
                >
                  <Panel key={openGeneration} onClose={closeModule} />
                </Suspense>
              ) : (
                <div className="flex flex-1 items-center justify-center gap-2 text-sm text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Cargando…
                </div>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
