"use client";

import { Loader2, PanelLeftClose, X } from "lucide-react";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { AnimatePresence, motion } from "framer-motion";

import { isModulesShellPilot } from "@/lib/pilot/modulesShell";
import {
  getModuleById,
  getPilotVisibleModules,
} from "@/modules/registry";
import type { CedModuleRegistration, ModulePanelProps } from "@/modules/types";

type LoadedPanel = ComponentType<ModulePanelProps>;

/**
 * Lateral module shell (signed-off):
 * - Left rail of square icons
 * - Drawer expands per module
 * - State discarded on close (unmount)
 * - Pilot-only; main CED UI unchanged
 */
export function ModuleShell() {
  const [enabled, setEnabled] = useState(false);
  const [modules, setModules] = useState<CedModuleRegistration[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  /** Bumps on each open so reopen always starts clean. */
  const [openGeneration, setOpenGeneration] = useState(0);
  const [Panel, setPanel] = useState<LoadedPanel | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const visible = isModulesShellPilot() ? getPilotVisibleModules() : [];
    setEnabled(visible.length > 0);
    setModules(visible);
  }, []);

  const active = useMemo(
    () => (activeId ? getModuleById(activeId) : undefined),
    [activeId],
  );

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

  if (!enabled || modules.length === 0) return null;

  return (
    <>
      {/* Left rail */}
      <aside
        className="pointer-events-auto fixed left-2 top-1/2 z-[70] flex -translate-y-1/2 flex-col gap-2 rounded-2xl border border-cyan-500/25 bg-[#060b14]/95 p-2 shadow-xl backdrop-blur-md sm:left-3"
        aria-label="Módulos piloto"
      >
        <div className="mb-0.5 px-0.5 text-center text-[8px] font-semibold uppercase tracking-wider text-amber-400/80">
          Piloto
        </div>
        {modules.map((m) => {
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
              className={`flex h-11 w-11 flex-col items-center justify-center rounded-xl border transition ${
                activeMod
                  ? "border-cyan-400/70 bg-cyan-500/20 text-cyan-100"
                  : "border-white/10 bg-white/5 text-slate-300 hover:border-cyan-500/40 hover:bg-white/10"
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

      <AnimatePresence>
        {activeId && active ? (
          <>
            <motion.button
              type="button"
              aria-label="Cerrar módulo"
              className="fixed inset-0 z-[74] bg-black/45"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={closeModule}
            />
            <motion.div
              key={`drawer-${activeId}-${openGeneration}`}
              role="dialog"
              aria-label={active.name}
              className="fixed bottom-0 left-0 top-0 z-[75] flex w-full flex-col border-r border-cyan-500/30 bg-[#0a1220] shadow-2xl sm:left-[3.75rem] sm:w-[min(58vw,52rem)]"
              initial={{ x: -28, opacity: 0.85 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: -40, opacity: 0 }}
              transition={{ type: "spring", stiffness: 380, damping: 34 }}
            >
              <header className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                <div className="flex items-center gap-2">
                  {(() => {
                    const ActiveIcon = active.icon;
                    return <ActiveIcon className="h-4 w-4 text-cyan-400" />;
                  })()}
                  <div>
                    <div className="text-sm font-semibold text-cyan-100">
                      {active.name}
                    </div>
                    <div className="text-[10px] uppercase tracking-wider text-amber-400/80">
                      Piloto — se descarta al cerrar
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={closeModule}
                    className="rounded p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"
                    aria-label="Cerrar drawer"
                    title="Cerrar"
                  >
                    <PanelLeftClose className="h-4 w-4 sm:hidden" />
                    <X className="hidden h-4 w-4 sm:block" />
                  </button>
                </div>
              </header>

              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {loadError ? (
                  <p className="p-4 text-[12px] text-red-400">{loadError}</p>
                ) : Panel ? (
                  <Suspense
                    fallback={
                      <div className="flex flex-1 items-center justify-center gap-2 text-[12px] text-slate-400">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Cargando…
                      </div>
                    }
                  >
                    <Panel key={openGeneration} onClose={closeModule} />
                  </Suspense>
                ) : (
                  <div className="flex flex-1 items-center justify-center gap-2 text-[12px] text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Cargando…
                  </div>
                )}
              </div>
            </motion.div>
          </>
        ) : null}
      </AnimatePresence>
    </>
  );
}
