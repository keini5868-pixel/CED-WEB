"use client";

import { MapPin, Navigation } from "lucide-react";

import type { NavRoute } from "@/lib/api/navigation";
import { formatMiles } from "@/lib/navigation/maneuvers";

import { NavigationBottomSheet } from "./NavigationBottomSheet";

type RoutePreviewPanelProps = {
  route: NavRoute;
  onStart: () => void;
  onCancel?: () => void;
  busy?: boolean;
};

export function RoutePreviewPanel({
  route,
  onStart,
  onCancel,
  busy = false,
}: RoutePreviewPanelProps) {
  return (
    <NavigationBottomSheet title={route.destination.label} onClose={onCancel}>
      <div className="px-4 py-3">
        <div className="mb-4 flex items-start gap-3">
          <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-50">
            <MapPin className="h-5 w-5 text-blue-700" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-lg font-semibold text-gray-900">{route.destination.label}</p>
            <p className="mt-1 text-base font-medium text-gray-800">
              {route.duration_text} · {formatMiles(route.distance_m)}
            </p>
            <p className="mt-1 text-sm text-gray-500">
              La ruta más rápida, tráfico habitual
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onStart}
          disabled={busy}
          className="inline-flex min-h-[52px] w-full items-center justify-center gap-2 rounded-full bg-[#1a7340] px-6 text-base font-bold text-white shadow-lg hover:bg-[#156632] disabled:opacity-50"
        >
          <Navigation className="h-5 w-5" />
          Iniciar
        </button>
      </div>
    </NavigationBottomSheet>
  );
}
