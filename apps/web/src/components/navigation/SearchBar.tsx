"use client";

import { ArrowRight, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { loadGoogleMaps } from "@/lib/maps/loadGoogleMaps";

type SearchBarProps = {
  onSearch: (query: string) => void;
  onPlaceSelect?: (place: { lat: number; lng: number; label: string }) => void;
  disabled?: boolean;
  placeholder?: string;
};

export function SearchBar({
  onSearch,
  onPlaceSelect,
  disabled = false,
  placeholder = "Escribe una dirección o lugar...",
}: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const autocompleteRef = useRef<google.maps.places.Autocomplete | null>(null);

  useEffect(() => {
    let cancelled = false;

    void loadGoogleMaps()
      .then(() => {
        if (cancelled || !inputRef.current || autocompleteRef.current) return;

        autocompleteRef.current = new google.maps.places.Autocomplete(
          inputRef.current,
          {
            fields: ["formatted_address", "geometry", "name"],
            types: ["geocode", "establishment"],
          },
        );

        autocompleteRef.current.addListener("place_changed", () => {
          const place = autocompleteRef.current?.getPlace();
          const loc = place?.geometry?.location;
          if (!loc) return;
          const label =
            place?.formatted_address || place?.name || inputRef.current?.value || "";
          setQuery(label);
          onPlaceSelect?.({
            lat: loc.lat(),
            lng: loc.lng(),
            label,
          });
        });
      })
      .catch(() => {
        /* autocompletado opcional si falla la carga */
      });

    return () => {
      cancelled = true;
    };
  }, [onPlaceSelect]);

  const submit = () => {
    const q = query.trim();
    if (!q || disabled) return;
    onSearch(q);
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border border-cyan-500/40 bg-black/85 px-3 py-2 shadow-lg backdrop-blur-md">
      <Search className="h-4 w-4 shrink-0 text-cyan-400" />
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
        disabled={disabled}
        placeholder={placeholder}
        className="min-w-0 flex-1 bg-transparent text-sm text-cyan-50 placeholder:text-cyan-700 focus:outline-none"
        autoComplete="off"
      />
      <button
        type="button"
        onClick={submit}
        disabled={disabled || !query.trim()}
        className="rounded border border-cyan-500/50 bg-cyan-950/60 p-2 text-cyan-300 transition hover:bg-cyan-900/60 disabled:opacity-40"
        aria-label="Buscar"
      >
        <ArrowRight className="h-4 w-4" />
      </button>
    </div>
  );
}
