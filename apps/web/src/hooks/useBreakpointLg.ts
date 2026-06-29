"use client";

import { useEffect, useState } from "react";

/** null hasta hidratar — evita montar dos layouts responsive a la vez. */
export function useBreakpointLg(): boolean | null {
  const [matches, setMatches] = useState<boolean | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const sync = () => setMatches(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  return matches;
}
