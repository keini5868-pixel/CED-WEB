"use client";

import type { HudState, PanelEvent } from "@ced/types";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";

import {
  connectPanelStream,
  EMPTY_PANELS,
  type HudPanelItem,
  type HudPanelsSnapshot,
} from "@/lib/api/panels";
import { HUD_BACKGROUND } from "@/lib/hud/hudBackgroundConfig";
import { useHudFeed } from "@/contexts/HudFeedContext";

type Action =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "event"; event: PanelEvent };

function itemFromPayload(payload: Record<string, unknown>): HudPanelItem {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title: String(payload.title ?? "Intel"),
    text: String(payload.text ?? ""),
    url: payload.url ? String(payload.url) : undefined,
  };
}

function reducePanels(state: HudPanelsSnapshot, action: Action): HudPanelsSnapshot {
  switch (action.type) {
    case "connected":
      return { ...state, streamConnected: true };
    case "disconnected":
      return { ...state, streamConnected: false };
    case "event": {
      const e = action.event;
      if (e.type === "search_started") {
        return {
          ...state,
          hudState: "searching",
          lastQuery: e.query,
          summary: "",
        };
      }
      if (e.type === "state") {
        return { ...state, hudState: e.hud };
      }
      if (e.type === "panel_item") {
        const item = itemFromPayload(e.payload);
        const key = e.panel === "city" ? "global" : e.panel;
        if (key === "global" || key === "drones" || key === "waves") {
          const list = [item, ...state[key]].slice(0, 12);
          return { ...state, [key]: list };
        }
        return state;
      }
      if (e.type === "summary_chunk") {
        return {
          ...state,
          hudState: "receiving",
          summary: `${state.summary}${state.summary ? " " : ""}${e.text}`.trim(),
        };
      }
      if (e.type === "search_complete") {
        return { ...state, hudState: "complete" };
      }
      return state;
    }
    default:
      return state;
  }
}

interface HudPanelContextValue extends HudPanelsSnapshot {
  dispatchPanelEvent: (event: PanelEvent) => void;
}

const HudPanelContext = createContext<HudPanelContextValue | null>(null);

export function HudPanelProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducePanels, EMPTY_PANELS);
  const { pushLine } = useHudFeed();

  const dispatchPanelEvent = useCallback((event: PanelEvent) => {
    dispatch({ type: "event", event });
  }, []);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let cancelled = false;

    const connectDelay = window.setTimeout(() => {
      void connectPanelStream(
        (event) => {
          dispatch({ type: "event", event });
          if (event.type === "summary_chunk") {
            pushLine(event.text, "report");
          }
        },
        () => {
          if (!cancelled) dispatch({ type: "disconnected" });
        },
      ).then((stop) => {
        if (cancelled) {
          stop();
          return;
        }
        cleanup = stop;
        dispatch({ type: "connected" });
      });
    }, HUD_BACKGROUND.panelStreamConnectDelayMs);

    return () => {
      cancelled = true;
      clearTimeout(connectDelay);
      cleanup?.();
      dispatch({ type: "disconnected" });
    };
  }, [pushLine]);

  const value = useMemo(
    () => ({
      ...state,
      dispatchPanelEvent,
    }),
    [state, dispatchPanelEvent],
  );

  return (
    <HudPanelContext.Provider value={value}>{children}</HudPanelContext.Provider>
  );
}

export function useHudPanels() {
  const ctx = useContext(HudPanelContext);
  if (!ctx) {
    throw new Error("useHudPanels debe usarse dentro de HudPanelProvider");
  }
  return ctx;
}

export function hudStateLabel(state: HudState): string {
  switch (state) {
    case "searching":
      return "Buscando…";
    case "receiving":
      return "Recibiendo intel…";
    case "complete":
      return "Consulta completa";
    default:
      return "En espera";
  }
}
