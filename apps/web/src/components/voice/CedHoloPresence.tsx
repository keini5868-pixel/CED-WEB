"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";

type CedHoloPresenceProps = {
  active: boolean;
  speaking: boolean;
};

type Spark = {
  x: number;
  y: number;
  tx: number;
  ty: number;
  t: number;
  speed: number;
  amp: number;
  phase: number;
  size: number;
  life: number;
};

const HOLO_SRC = "/voice/holo-presence.png";

function spawnSpark(ox: number, oy: number, tx: number, ty: number): Spark {
  return {
    x: ox + (Math.random() - 0.5) * 8,
    y: oy + (Math.random() - 0.5) * 8,
    tx: tx + (Math.random() - 0.5) * 28,
    ty: ty + (Math.random() - 0.5) * 36,
    t: 0,
    speed: 0.022 + Math.random() * 0.028,
    amp: 8 + Math.random() * 22,
    phase: Math.random() * Math.PI * 2,
    size: 2 + Math.random() * 3,
    life: 1,
  };
}

function HoloFace({ speaking }: { speaking: boolean }) {
  const mouthRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    let t = 0;
    const tick = () => {
      t += 0.045;
      const talk = speaking
        ? 0.1 +
          Math.abs(Math.sin(t * 11.2)) * 0.32 +
          Math.abs(Math.sin(t * 23.7 + 0.4)) * 0.22
        : 0.03 + Math.sin(t * 1.4) * 0.012;
      if (mouthRef.current) {
        mouthRef.current.style.transform = `scaleY(${1 + talk * 0.42})`;
      }
      if (glowRef.current) {
        glowRef.current.style.opacity = String(0.05 + talk * 0.42);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking]);

  return (
    <div className="relative w-[min(72vw,17rem)] sm:w-[19rem] lg:w-[22rem]">
      <div className="absolute inset-[8%] rounded-full bg-[#4fd4ee]/25 blur-3xl" />
      <div className="relative drop-shadow-[0_0_24px_rgba(79,212,238,0.9)]">
        <img
          src={HOLO_SRC}
          alt=""
          className="pointer-events-none relative z-[1] h-auto w-full select-none object-contain"
        />
        <div
          ref={mouthRef}
          className="absolute inset-0 z-[2] origin-[50%_58%]"
          style={{ clipPath: "inset(52% 28% 28% 28%)" }}
        >
          <img src={HOLO_SRC} alt="" className="h-auto w-full object-contain" />
        </div>
        <div
          ref={glowRef}
          className="absolute left-1/2 top-[58%] z-[3] h-8 w-24 -translate-x-1/2 rounded-full bg-[#7ae7ff] blur-md"
        />
      </div>
    </div>
  );
}

/** Retrato holográfico + un destello de partículas desde ESCUCHAR. */
export function CedHoloPresence({ active, speaking }: CedHoloPresenceProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const faceRef = useRef<HTMLDivElement>(null);
  const sparksRef = useRef<Spark[]>([]);
  const activeRef = useRef(active);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let lastSpawn = 0;
    let burstLeft = 0;
    let armed = true;

    const resize = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(r.width * dpr));
      canvas.height = Math.max(1, Math.floor(r.height * dpr));
      canvas.style.width = `${r.width}px`;
      canvas.style.height = `${r.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const origins = () => {
      const root = wrap.getBoundingClientRect();
      const btn = document.querySelector<HTMLElement>("[data-ced-listen]");
      const face = faceRef.current?.getBoundingClientRect();
      const ox = btn ? btn.getBoundingClientRect().left + btn.offsetWidth / 2 - root.left : root.width - 48;
      const oy = btn ? btn.getBoundingClientRect().top + btn.offsetHeight / 2 - root.top : root.height * 0.62;
      const tx = face ? face.left + face.width / 2 - root.left : root.width * 0.38;
      const ty = face ? face.top + face.height * 0.42 - root.top : root.height * 0.42;
      return { ox, oy, tx, ty };
    };

    const tick = (now: number) => {
      const r = wrap.getBoundingClientRect();
      ctx.clearRect(0, 0, r.width, r.height);
      const { ox, oy, tx, ty } = origins();
      const on = activeRef.current;

      if (!on) {
        burstLeft = 0;
        armed = true;
      } else if (armed) {
        armed = false;
        burstLeft = 42;
      }

      if (on && burstLeft > 0 && now - lastSpawn > 24) {
        lastSpawn = now;
        const n = Math.min(8, burstLeft);
        for (let i = 0; i < n; i += 1) sparksRef.current.push(spawnSpark(ox, oy, tx, ty));
        burstLeft -= n;
      }

      const next: Spark[] = [];
      for (const p of sparksRef.current) {
        p.t += p.speed;
        const u = Math.min(1, p.t);
        const ease = 1 - (1 - u) * (1 - u);
        const dx = p.tx - p.x;
        const dy = p.ty - p.y;
        const len = Math.hypot(dx, dy) || 1;
        const px = p.x + dx * ease;
        const py = p.y + dy * ease;
        const wave = Math.sin(u * 9 + p.phase) * p.amp * (1 - u);
        const x = px + (-dy / len) * wave;
        const y = py + (dx / len) * wave;
        p.life = on ? 1 - u : p.life - 0.06;
        if (p.life <= 0 || u >= 1) continue;
        next.push(p);
        ctx.beginPath();
        ctx.fillStyle = `rgba(180, 245, 255, ${0.45 + p.life * 0.55})`;
        ctx.shadowColor = "#7ae7ff";
        ctx.shadowBlur = 14;
        ctx.arc(x, y, p.size + 0.8, 0, Math.PI * 2);
        ctx.fill();
      }
      sparksRef.current = next;
      ctx.shadowBlur = 0;
      raf = requestAnimationFrame(tick);
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      className="pointer-events-none absolute inset-0 z-[80] h-full w-full overflow-hidden"
      aria-hidden
    >
      <canvas ref={canvasRef} className="absolute inset-0" />
      <div className="absolute inset-0 flex items-center justify-center pr-[6.5rem] sm:pr-[8rem] lg:pr-[min(15.5rem,28vw)]">
        <AnimatePresence>
          {active ? (
            <motion.div
              ref={faceRef}
              key="ced-holo-face"
              initial={{ opacity: 0, scale: 0.86 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.94 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="-translate-y-[6%]"
            >
              <HoloFace speaking={speaking} />
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
