"use client";

import { useCallback, useEffect, useState } from "react";

const POLL_MS = 8_000;

/** Poll de no leídos + refresco al volver a la pestaña. */
export function useSupportUnreadPoll(
  fetchCount: () => Promise<number>,
  enabled = true,
) {
  const [unreadCount, setUnreadCount] = useState(0);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      const count = await fetchCount();
      setUnreadCount(count);
    } catch {
      /* ignore */
    }
  }, [enabled, fetchCount]);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const interval = window.setInterval(() => void refresh(), POLL_MS);
    const onFocus = () => void refresh();
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, refresh]);

  return { unreadCount, setUnreadCount, refresh };
}
