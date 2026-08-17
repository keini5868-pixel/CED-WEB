"use client";



import { motion } from "framer-motion";

import { useEffect, useState } from "react";



import type { OrbState, VoicePaletteId } from "@ced/types";



import { paletteColors } from "@/components/orb/orbPalette";



type Spark = {

  id: number;

  left: number;

  top: number;

  delay: number;

  dur: number;

  size: number;

};



const SPARK_COUNT = 16;



/** Chispas solo en cliente — cero SSR, cero hydration mismatch. */

function CedOrbSparkles({

  palette,

  active,

}: {

  palette: VoicePaletteId;

  active: boolean;

}) {

  const [sparks, setSparks] = useState<Spark[]>([]);

  const [mounted, setMounted] = useState(false);

  const colors = paletteColors(palette);



  useEffect(() => {

    setMounted(true);

    const generated: Spark[] = Array.from({ length: SPARK_COUNT }, (_, i) => ({

      id: i,

      left: 8 + Math.random() * 84,

      top: 8 + Math.random() * 84,

      delay: Math.random() * 2.8,

      dur: 1.1 + Math.random() * 1.9,

      size: 2 + Math.random() * 3,

    }));

    setSparks(generated);

  }, [palette]);



  if (!mounted || sparks.length === 0) return null;



  return (

    <div className="pointer-events-none absolute inset-0" aria-hidden suppressHydrationWarning>

      {sparks.map((s) => (

        <span

          key={s.id}

          className="ced-orb-spark absolute rounded-full"

          style={{

            left: `${s.left}%`,

            top: `${s.top}%`,

            width: s.size,

            height: s.size,

            background: colors.primary,

            animationDelay: `${s.delay}s`,

            animationDuration: `${s.dur}s`,

            opacity: active ? 0.85 : 0.35,

          }}

        />

      ))}

    </div>

  );

}



interface CedOrbOverlayProps {

  orbState: OrbState;

  audioLevel: number;

  palette: VoicePaletteId;

}



export function CedOrbOverlay({

  orbState,

  audioLevel,

  palette,

}: CedOrbOverlayProps) {

  const colors = paletteColors(palette);

  const active =

    orbState === "listening" ||

    orbState === "speaking" ||

    orbState === "processing";



  return (

    <div

      className="pointer-events-none absolute inset-0 flex items-center justify-center"

      aria-hidden

    >

      <CedOrbSparkles palette={palette} active={active} />



      <motion.span

        className="relative z-10 select-none font-[family-name:var(--font-orbitron)] font-bold tracking-[0.1em]"

        style={{

          color: colors.primary,

          textShadow: `0 0 18px ${colors.primary}, 0 0 36px ${colors.secondary}66`,

          fontSize: "clamp(1.35rem, 4.2vw, 1.85rem)",

        }}

        animate={{

          scale: 1 + audioLevel * 0.12,

          opacity: 0.72 + audioLevel * 0.28,

          rotateZ:

            orbState === "processing"

              ? [0, 1.5, -1.5, 0]

              : audioLevel * 2 - 1,

        }}

        transition={{

          scale: { duration: 0.12 },

          opacity: { duration: 0.15 },

          rotateZ:

            orbState === "processing"

              ? { repeat: Infinity, duration: 2.5 }

              : { duration: 0.12 },

        }}

      >

        CED

      </motion.span>

    </div>

  );

}


