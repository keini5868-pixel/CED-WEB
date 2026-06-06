"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";

/** Mini gráfico de barras animado — panel CITY. */
export function HudCityPulse() {
  const [bars, setBars] = useState([32, 48, 28, 56, 40, 52, 36]);

  useEffect(() => {
    const id = setInterval(() => {
      setBars((prev) =>
        prev.map((v) => {
          const delta = (Math.random() - 0.45) * 18;
          return Math.max(12, Math.min(72, v + delta));
        }),
      );
    }, 2200);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex h-full min-h-[160px] flex-col justify-between gap-4">
      <p className="ced-hud-text-secondary text-xs">
        Pulso local · actividad del castillo
      </p>
      <div className="flex flex-1 items-end justify-center gap-2 px-2 pb-2">
        {bars.map((h, i) => (
          <motion.div
            key={i}
            className="w-4 max-w-[14%] rounded-t bg-gradient-to-t from-cyan-900 to-cyan-400/90"
            animate={{ height: `${h}%` }}
            transition={{ duration: 0.9, ease: "easeInOut" }}
            style={{ height: `${h}%`, minHeight: 8 }}
          />
        ))}
      </div>
      <div className="flex items-center justify-between text-[10px] text-cyan-700/90">
        <span className="font-[family-name:var(--font-orbitron)] tracking-widest">
          NODES
        </span>
        <span className="ced-hud-text-muted">sync · live</span>
      </div>
    </div>
  );
}
