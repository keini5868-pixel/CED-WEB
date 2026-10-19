"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type SentinelExtStats,
  type SentinelPolicy,
  SENTINEL_EXT_SOURCE,
  SENTINEL_HUD_SOURCE,
  decodePolicyShare,
  emptyExtStats,
  loadSentinelPolicy,
  saveSentinelPolicy,
} from "@/lib/sentinel/policy";

export function useSentinelPolicy() {
  const [policy, setPolicy] = useState<SentinelPolicy>(loadSentinelPolicy);
  const [stats, setStats] = useState<SentinelExtStats>(emptyExtStats);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("policy") || params.get("invite");
    if (token) {
      const imported = decodePolicyShare(token);
      if (imported) setPolicy(saveSentinelPolicy(imported));
    }
    window.postMessage({ source: SENTINEL_HUD_SOURCE, type: "PING" }, "*");

    const onMsg = (ev: MessageEvent) => {
      const data = ev.data as {
        source?: string;
        type?: string;
        stats?: Partial<SentinelExtStats>;
      };
      if (data?.source !== SENTINEL_EXT_SOURCE) return;
      if (data.type === "PONG" || data.type === "STATS") {
        setStats({
          ...emptyExtStats(),
          ...data.stats,
          connected: true,
        });
      }
    };
    window.addEventListener("message", onMsg);
    const ping = window.setInterval(() => {
      window.postMessage({ source: SENTINEL_HUD_SOURCE, type: "PING" }, "*");
    }, 4000);
    return () => {
      window.removeEventListener("message", onMsg);
      window.clearInterval(ping);
    };
  }, []);

  const patch = useCallback((partial: Partial<SentinelPolicy>) => {
    setPolicy((cur) => saveSentinelPolicy({ ...cur, ...partial }));
  }, []);

  return { policy, patch, stats };
}
