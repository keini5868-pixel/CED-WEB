"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Navigation, Phone, Star } from "lucide-react";

import type { NavPlaceOption } from "@/lib/api/navigation";

import { NavigationBottomSheet } from "./NavigationBottomSheet";

type PlaceOptionsListProps = {
  query: string;
  places: NavPlaceOption[];
  onStart: (index: number) => void;
  onCancel: () => void;
  busy?: boolean;
};

function formatRating(rating?: number, count?: number): string | null {
  if (rating == null) return null;
  const stars = rating.toFixed(1);
  if (count != null && count > 0) {
    return `${stars} (${count.toLocaleString("es")})`;
  }
  return stars;
}

function statusLine(place: NavPlaceOption): string {
  const parts: string[] = [];
  if (place.open_now === true) {
    parts.push("Abierto");
    if (place.hours_text) parts.push(place.hours_text);
  } else if (place.open_now === false) {
    parts.push("Cerrado");
  }
  if (place.distance_text) parts.push(place.distance_text);
  return parts.join(" · ");
}

export function PlaceOptionsList({
  query,
  places,
  onStart,
  onCancel,
  busy = false,
}: PlaceOptionsListProps) {
  const [openNowOnly, setOpenNowOnly] = useState(false);

  const title = query.trim() ? query : "Resultados";

  const visiblePlaces = useMemo(() => {
    return places
      .map((place, index) => ({ place, index }))
      .filter(({ place }) => !openNowOnly || place.open_now === true);
  }, [openNowOnly, places]);

  if (!places.length) return null;

  return (
    <NavigationBottomSheet title={title} onClose={onCancel}>
      <div className="flex gap-2 overflow-x-auto px-4 py-3">
        <button
          type="button"
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700"
        >
          Ordenar por
          <ChevronDown className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => setOpenNowOnly((v) => !v)}
          className={`inline-flex shrink-0 items-center rounded-full border px-3 py-1.5 text-xs font-medium ${
            openNowOnly
              ? "border-teal-600 bg-teal-50 text-teal-800"
              : "border-gray-200 bg-gray-50 text-gray-700"
          }`}
        >
          Abierto ahora
        </button>
      </div>

      {openNowOnly && visiblePlaces.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-gray-500">
          No hay lugares abiertos ahora con ese filtro.
        </p>
      ) : null}

      <ul className="divide-y divide-gray-100">
        {visiblePlaces.map(({ place, index }) => {
          const ratingLabel = formatRating(place.rating, place.rating_count);
          const status = statusLine(place);
          const phone = place.phone?.trim();

          return (
            <li key={`${place.place_id || place.name}-${index}`} className="px-4 py-4">
              <div className="mb-1 flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-base font-semibold leading-snug text-gray-900">
                    {place.name}
                  </p>
                  {place.category ? (
                    <p className="mt-0.5 text-sm text-gray-500">{place.category}</p>
                  ) : null}
                </div>
                {ratingLabel ? (
                  <span className="inline-flex shrink-0 items-center gap-0.5 text-sm text-gray-700">
                    {ratingLabel}
                    <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                  </span>
                ) : null}
              </div>

              {status ? (
                <p className="text-sm text-gray-600">{status}</p>
              ) : null}

              {place.address ? (
                <p className="mt-1 line-clamp-2 text-sm text-gray-500">{place.address}</p>
              ) : null}

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onStart(index)}
                  disabled={busy}
                  className="inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-full bg-teal-600 px-4 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50 sm:flex-none sm:px-5"
                >
                  <Navigation className="h-4 w-4" />
                  Cómo llegar
                </button>
                {phone ? (
                  <a
                    href={`tel:${phone.replace(/\s+/g, "")}`}
                    className="inline-flex min-h-10 flex-1 items-center justify-center gap-2 rounded-full border border-teal-200 bg-teal-50 px-4 text-sm font-semibold text-teal-800 hover:bg-teal-100 sm:flex-none sm:px-5"
                  >
                    <Phone className="h-4 w-4" />
                    Llamar
                  </a>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </NavigationBottomSheet>
  );
}
