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

function spawnSpark(ox: number, oy: number, tx: number, ty: number): Spark {
  return {
    x: ox + (Math.random() - 0.5) * 10,
    y: oy + (Math.random() - 0.5) * 10,
    tx: tx + (Math.random() - 0.5) * 36,
    ty: ty + (Math.random() - 0.5) * 48,
    t: 0,
    speed: 0.01 + Math.random() * 0.018,
    amp: 10 + Math.random() * 28,
    phase: Math.random() * Math.PI * 2,
    size: 2.2 + Math.random() * 3.4,
    life: 1,
  };
}

function HoloFace({ speaking }: { speaking: boolean }) {
  const mouthRef = useRef<SVGEllipseElement>(null);
  const glowRef = useRef<SVGEllipseElement>(null);

  useEffect(() => {
    let raf = 0;
    let t = 0;
    const tick = () => {
      t += 0.045;
      const talk = speaking
        ? 0.12 +
          Math.abs(Math.sin(t * 11.2)) * 0.38 +
          Math.abs(Math.sin(t * 23.7 + 0.4)) * 0.28 +
          Math.abs(Math.sin(t * 5.1)) * 0.12
        : 0.06 + Math.sin(t * 1.4) * 0.02;
      if (mouthRef.current) {
        mouthRef.current.setAttribute("ry", String(3.2 + talk * 16));
        mouthRef.current.setAttribute("rx", String(18 + talk * 6));
      }
      if (glowRef.current) {
        glowRef.current.setAttribute("opacity", String(0.18 + talk * 0.35));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking]);

  return (
    <svg
      viewBox="0 0 200 268"
      className="h-auto w-[min(58vw,14rem)] drop-shadow-[0_0_32px_rgba(79,212,238,0.85)] sm:w-[16rem] lg:w-[18.5rem]"
      aria-hidden
    >
      <defs>
        <clipPath id="ced-holo-head">
          <ellipse cx="100" cy="118" rx="68" ry="90" />
        </clipPath>
        <radialGradient id="ced-holo-skin" cx="50%" cy="38%" r="68%">
          <stop offset="0%" stopColor="#9af0ff" stopOpacity="0.55" />
          <stop offset="45%" stopColor="#1a6a7c" stopOpacity="0.72" />
          <stop offset="100%" stopColor="#06323c" stopOpacity="0.88" />
        </radialGradient>
        <linearGradient id="ced-holo-scan" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4fd4ee" stopOpacity="0" />
          <stop offset="50%" stopColor="#4fd4ee" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#4fd4ee" stopOpacity="0" />
        </linearGradient>
      </defs>

      <ellipse cx="100" cy="118" rx="76" ry="98" fill="#4fd4ee" fillOpacity="0.12" />
      <ellipse cx="100" cy="118" rx="74" ry="96" fill="none" stroke="#7ae7ff" strokeOpacity="0.7" strokeWidth="2" />
      <ellipse cx="100" cy="118" rx="68" ry="90" fill="url(#ced-holo-skin)" stroke="#4fd4ee" strokeWidth="2" />

      <g clipPath="url(#ced-holo-head)" opacity="0.55">
        {Array.from({ length: 14 }, (_, i) => (
          <line
            key={`h-${i}`}
            x1="28"
            y1={40 + i * 13}
            x2="172"
            y2={40 + i * 13}
            stroke="#4fd4ee"
            strokeWidth="0.4"
            strokeOpacity="0.35"
          />
        ))}
        {Array.from({ length: 11 }, (_, i) => (
          <path
            key={`c-${i}`}
            d={`M${42 + i * 11} 32 C ${50 + i * 10} 118, ${50 + i * 10} 118, ${42 + i * 11} 208`}
            fill="none"
            stroke="#4fd4ee"
            strokeWidth="0.35"
            strokeOpacity="0.28"
          />
        ))}
        <rect x="28" y="70" width="144" height="18" fill="url(#ced-holo-scan)">
          <animate attributeName="y" values="38;190;38" dur="3.6s" repeatCount="indefinite" />
        </rect>
      </g>

      {/* Logo CED en la frente */}
      <g transform="translate(100 58)">
        <circle r="16" fill="#042830" stroke="#4fd4ee" strokeWidth="1.6" />
        <circle r="16" fill="none" stroke="#7ae7ff" strokeWidth="0.6" opacity="0.7" />
        <circle r="6.2" fill="#4fd4ee" />
        <circle r="2.4" fill="#e8fbff" />
        <text
          y="28"
          textAnchor="middle"
          fill="#4fd4ee"
          fontSize="7.5"
          fontFamily="var(--font-orbitron), sans-serif"
          letterSpacing="2.2"
        >
          CED
        </text>
      </g>

      {/* Ojos */}
      <ellipse cx="74" cy="112" rx="11" ry="7.5" fill="#031018" stroke="#7ae7ff" strokeWidth="1.1" />
      <ellipse cx="126" cy="112" rx="11" ry="7.5" fill="#031018" stroke="#7ae7ff" strokeWidth="1.1" />
      <ellipse cx="74" cy="112" rx="4.2" ry="4.2" fill="#4fd4ee">
        <animate attributeName="opacity" values="0.75;1;0.75" dur="2.4s" repeatCount="indefinite" />
      </ellipse>
      <ellipse cx="126" cy="112" rx="4.2" ry="4.2" fill="#4fd4ee">
        <animate attributeName="opacity" values="0.75;1;0.75" dur="2.4s" repeatCount="indefinite" />
      </ellipse>
      <circle cx="75.5" cy="110.5" r="1.3" fill="#e8fbff" />
      <circle cx="127.5" cy="110.5" r="1.3" fill="#e8fbff" />

      {/* Nariz */}
      <path d="M100 118 L94 142 L100 146 L106 142 Z" fill="none" stroke="#4fd4ee" strokeWidth="0.9" opacity="0.85" />

      {/* Boca — ry/rx animados por volumen simulado */}
      <ellipse
        ref={glowRef}
        cx="100"
        cy="176"
        rx="26"
        ry="10"
        fill="#4fd4ee"
        opacity="0.2"
      />
      <ellipse
        ref={mouthRef}
        cx="100"
        cy="176"
        rx="20"
        ry="4"
        fill="#021016"
        stroke="#7ae7ff"
        strokeWidth="1.3"
      />
      <path d="M82 176 Q100 180 118 176" fill="none" stroke="#4fd4ee" strokeWidth="0.6" opacity="0.7" />

      {/* Cuello / hombros wireframe */}
      <path d="M78 204 C 70 230, 48 248, 22 258" fill="none" stroke="#4fd4ee" strokeWidth="1" opacity="0.45" />
      <path d="M122 204 C 130 230, 152 248, 178 258" fill="none" stroke="#4fd4ee" strokeWidth="1" opacity="0.45" />
      <path d="M88 208 C 92 228, 108 228, 112 208" fill="none" stroke="#4fd4ee" strokeWidth="0.8" opacity="0.4" />
    </svg>
  );
}

/** Presencia holográfica de CED: rayas desde ESCUCHAR + rostro que habla. */
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

      if (on && burstLeft === 0 && sparksRef.current.length === 0) {
        burstLeft = 36;
      }
      if (!on) burstLeft = 0;

      if (on && now - lastSpawn > 48) {
        lastSpawn = now;
        const n = burstLeft > 0 ? 5 : 2;
        for (let i = 0; i < n; i += 1) sparksRef.current.push(spawnSpark(ox, oy, tx, ty));
        burstLeft = Math.max(0, burstLeft - n);
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
        p.life = on ? 1 - u : p.life - 0.04;
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
              initial={{ opacity: 0, scale: 0.78 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
              className="-translate-y-[8%]"
            >
              <HoloFace speaking={speaking} />
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
