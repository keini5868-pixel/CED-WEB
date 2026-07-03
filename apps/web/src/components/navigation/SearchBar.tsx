"use client";

import { ArrowRight, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { suggestNavigationPlaces } from "@/lib/api/navigation";

type Suggestion = {
  label: string;
  address?: string;
  lat: number;
  lng: number;
};

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
  placeholder = "Busca un lugar...",
}: SearchBarProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const debounceRef = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (ev: MouseEvent) => {
      if (!containerRef.current?.contains(ev.target as Node)) {
        setSuggestOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    const q = query.trim();
    if (q.length < 2 || disabled) {
      setSuggestions([]);
      setSuggestOpen(false);
      return;
    }

    debounceRef.current = window.setTimeout(() => {
      void suggestNavigationPlaces(q)
        .then((res) => {
          const items = res.suggestions || [];
          setSuggestions(items);
          setSuggestOpen(items.length > 0);
        })
        .catch(() => {
          setSuggestions([]);
          setSuggestOpen(false);
        });
    }, 320);

    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query, disabled]);

  const submit = () => {
    const q = query.trim();
    if (!q || disabled) return;
    setSuggestOpen(false);
    onSearch(q);
  };

  const pickSuggestion = (item: Suggestion) => {
    setQuery(item.label);
    setSuggestOpen(false);
    setSuggestions([]);
    onPlaceSelect?.({
      lat: item.lat,
      lng: item.lng,
      label: item.label,
    });
  };

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-2 rounded-lg border border-cyan-500/40 bg-black/85 px-3 py-2 shadow-lg backdrop-blur-md">
        <Search className="h-4 w-4 shrink-0 text-cyan-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (suggestions.length) setSuggestOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setSuggestOpen(false);
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

      {suggestOpen && suggestions.length > 0 ? (
        <ul className="absolute left-0 right-0 top-full z-[120] mt-1 max-h-52 overflow-y-auto rounded-lg border border-cyan-500/30 bg-black/95 py-1 shadow-xl">
          {suggestions.map((item, idx) => (
            <li key={`${item.label}-${idx}`}>
              <button
                type="button"
                onClick={() => pickSuggestion(item)}
                className="block w-full px-3 py-2 text-left hover:bg-cyan-950/50"
              >
                <span className="block text-sm text-cyan-100">{item.label}</span>
                {item.address && item.address !== item.label ? (
                  <span className="block text-xs text-cyan-600">{item.address}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
