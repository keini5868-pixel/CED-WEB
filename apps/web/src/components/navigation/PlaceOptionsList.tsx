"use client";

import { MapPin, Navigation, X } from "lucide-react";

import type { NavPlaceOption } from "@/lib/api/navigation";

type PlaceOptionsListProps = {
  query: string;
  places: NavPlaceOption[];
  onStart: (index: number) => void;
  onCancel: () => void;
  busy?: boolean;
};

export function PlaceOptionsList({
  query,
  places,
  onStart,
  onCancel,
  busy = false,
}: PlaceOptionsListProps) {
  if (!places.length) return null;

  const title = query.trim()
    ? `${query.toUpperCase()} MÁS CERCANOS`
    : "LUGARES CERCANOS";

  return (
    <div className="rounded-lg border border-cyan-500/35 bg-black/90 p-3 shadow-xl backdrop-blur-md">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-cyan-400" />
          <p className="font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-300 sm:text-xs">
            {title}
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded border border-red-500/40 px-2 py-1 text-[10px] font-bold tracking-wide text-red-300 hover:bg-red-950/40"
        >
          <span className="inline-flex items-center gap-1">
            <X className="h-3 w-3" />
            CANCELAR
          </span>
        </button>
      </div>

      <ul className="space-y-2">
        {places.map((place, index) => (
          <li
            key={`${place.place_id || place.name}-${index}`}
            className="rounded border border-cyan-500/20 bg-cyan-950/20 p-2.5"
          >
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="text-sm font-semibold text-cyan-100">
                {index + 1}. {place.name}
              </span>
              {place.distance_text ? (
                <span className="shrink-0 text-xs text-cyan-400">
                  {place.distance_text}
                </span>
              ) : null}
            </div>
            {place.address ? (
              <p className="mb-2 text-xs text-cyan-600">{place.address}</p>
            ) : null}
            <button
              type="button"
              onClick={() => onStart(index)}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded border border-cyan-400/50 bg-cyan-900/40 px-3 py-1.5 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-widest text-cyan-200 hover:bg-cyan-800/50 disabled:opacity-50"
            >
              <Navigation className="h-3 w-3" />
              INICIAR VIAJE
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
