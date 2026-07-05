"use client";

import { Bookmark, MapPin, Navigation, Plus } from "lucide-react";

import type { NavRoute } from "@/lib/api/navigation";

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
    <NavigationBottomSheet
      title={route.destination.label}
      onClose={onCancel}
    >
      <div className="px-4 py-3">
        <div className="mb-4 flex items-start gap-3">
          <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-teal-50">
            <MapPin className="h-5 w-5 text-teal-700" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-teal-700">
              {route.duration_text} · {route.distance_text}
            </p>
            <p className="mt-1 text-sm text-gray-600">
              La ruta más rápida, tráfico habitual
            </p>
            <p className="mt-2 line-clamp-2 text-xs text-gray-500">
              {route.destination.label}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onStart}
            disabled={busy}
            className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-full bg-teal-600 px-5 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50 sm:flex-none"
          >
            <Navigation className="h-4 w-4" />
            Iniciar
          </button>
          <button
            type="button"
            onClick={onStart}
            disabled={busy}
            className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-4 text-sm font-semibold text-teal-800 hover:bg-teal-100 disabled:opacity-50 sm:flex-none"
          >
            Cómo llegar
          </button>
          <button
            type="button"
            disabled
            title="Próximamente"
            className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-4 text-sm font-medium text-gray-400"
          >
            <Plus className="h-4 w-4" />
            Paradas
          </button>
          <button
            type="button"
            disabled
            title="Próximamente"
            className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-4 text-sm font-medium text-gray-400"
          >
            <Bookmark className="h-4 w-4" />
            Guardar
          </button>
        </div>
      </div>
    </NavigationBottomSheet>
  );
}
