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

const HOLO_SRC = "/voice/holo-presence.png?v=mesh3";
const FORM_DELAY = 0.45;
const FORM_DURATION = 2.15;
const formEase = [0.22, 0.84, 0.32, 1] as const;

function spawnSpark(ox: number, oy: number, tx: number, ty: number): Spark {
  return {
    x: ox + (Math.random() - 0.5) * 8,
    y: oy + (Math.random() - 0.5) * 8,
    tx: tx + (Math.random() - 0.5) * 28,
    ty: ty + (Math.random() - 0.5) * 36,
    t: 0,
    speed: 0.007 + Math.random() * 0.007,
    amp: 8 + Math.random() * 22,
    phase: Math.random() * Math.PI * 2,
    size: 2 + Math.random() * 3,
    life: 1,
  };
}

function HoloFace({ speaking }: { speaking: boolean }) {
  const ringSpeed = speaking ? 1.35 : 2.8;
  const spinSpeed = speaking ? 9 : 22;
  const formed = FORM_DELAY + FORM_DURATION * 0.55;

  return (
    <div className="relative w-[min(78vw,19rem)] sm:w-[21rem] lg:w-[24rem]">
      <div className="absolute inset-[16%] rounded-full bg-[#4fd4ee]/18 blur-3xl" />

      <motion.div
        className="relative overflow-hidden"
        initial={{ clipPath: "inset(100% 0 0 0)" }}
        animate={{ clipPath: "inset(0% 0 0 0)" }}
        transition={{ duration: FORM_DURATION, delay: FORM_DELAY, ease: formEase }}
      >
        {[0, 1, 2, 3].map((i) => (
          <motion.div
            key={`echo-${i}`}
            className="absolute left-1/2 top-[46%] z-0 h-[70%] w-[58%] -translate-x-1/2 -translate-y-1/2 rounded-[46%] border border-[#7ae7ff]/45"
            initial={{ scale: 1, opacity: 0 }}
            animate={{ scale: [1, 1.28], opacity: [0.5, 0] }}
            transition={{
              duration: ringSpeed,
              delay: formed + i * (ringSpeed / 4),
              repeat: Infinity,
              ease: "easeOut",
            }}
          />
        ))}

        <motion.div
          className="absolute left-[8%] right-[8%] top-[4%] bottom-[14%] z-0 rounded-[46%] border border-dashed border-[#4fd4ee]/55"
          animate={{ rotate: 360 }}
          transition={{ duration: spinSpeed, delay: formed, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          className="absolute left-[16%] right-[16%] top-[10%] bottom-[20%] z-0 rounded-[46%] border border-dotted border-[#7ae7ff]/40"
          animate={{ rotate: -360 }}
          transition={{ duration: spinSpeed * 1.35, delay: formed, repeat: Infinity, ease: "linear" }}
        />

        <div className="relative z-[1] drop-shadow-[0_0_22px_rgba(79,212,238,0.85)]">
          <motion.img
            src={HOLO_SRC}
            alt=""
            className="pointer-events-none h-auto w-full select-none object-contain"
            animate={{ y: [0, -5, 0] }}
            transition={{ duration: 4.6, delay: FORM_DELAY + FORM_DURATION, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.div
            className="absolute left-[12%] right-[12%] h-8 bg-gradient-to-b from-transparent via-[#7ae7ff]/35 to-transparent"
            animate={{ top: ["10%", "72%", "10%"] }}
            transition={{
              duration: speaking ? 2.2 : 4.4,
              delay: FORM_DELAY + FORM_DURATION,
              repeat: Infinity,
              ease: "linear",
            }}
          />
          <div
            className="absolute left-1/2 top-[35.5%] z-[3] h-[2.75rem] w-[2.75rem] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-full sm:h-12 sm:w-12"
            style={{
              background:
                "radial-gradient(circle at 50% 38%, rgba(79,212,238,0.22), rgba(3,18,26,0.94) 68%)",
              boxShadow: "inset 0 0 0 1px rgba(122,231,255,0.28)",
            }}
          >
            <div
              className="absolute inset-0 opacity-60"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(to bottom, rgba(79,212,238,0.4) 0px, rgba(79,212,238,0.4) 1px, transparent 1px, transparent 4px), repeating-linear-gradient(to right, rgba(79,212,238,0.28) 0px, rgba(79,212,238,0.28) 1px, transparent 1px, transparent 5px)",
              }}
            />
          </div>
          <div className="absolute left-1/2 top-[88%] z-[4] -translate-x-1/2 -translate-y-1/2">
            <motion.svg
              viewBox="0 0 64 78"
              className="h-11 w-11 drop-shadow-[0_0_10px_rgba(122,231,255,0.95)] sm:h-12 sm:w-12"
              animate={{ opacity: [0.85, 1, 0.85], scale: [1, 1.06, 1] }}
              transition={{ duration: 2.4, delay: formed, repeat: Infinity, ease: "easeInOut" }}
              aria-hidden
            >
              <circle cx="32" cy="28" r="18" fill="#042830" fillOpacity="0.55" stroke="#7ae7ff" strokeWidth="2.2" />
              <circle cx="32" cy="28" r="18" fill="none" stroke="#e8fbff" strokeWidth="0.7" opacity="0.7" />
              <circle cx="32" cy="28" r="7.2" fill="#4fd4ee" />
              <circle cx="32" cy="28" r="2.6" fill="#e8fbff" />
              <text
                x="32"
                y="62"
                textAnchor="middle"
                fill="#7ae7ff"
                fontSize="11"
                fontFamily="var(--font-orbitron), sans-serif"
                letterSpacing="3"
              >
                CED
              </text>
            </motion.svg>
          </div>

          {speaking
            ? [0, 1, 2].map((i) => (
                <motion.div
                  key={`voice-${i}`}
                  className="absolute left-1/2 top-[68%] z-[3] h-5 w-[4.25rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-[#7ae7ff]/70"
                  initial={{ scale: 0.55, opacity: 0.7 }}
                  animate={{ scale: [0.55, 1.55], opacity: [0.7, 0] }}
                  transition={{
                    duration: 0.7,
                    delay: i * 0.22,
                    repeat: Infinity,
                    ease: "easeOut",
                  }}
                />
              ))
            : null}
        </div>
      </motion.div>

      <motion.div
        className="pointer-events-none absolute left-[6%] right-[6%] z-[6] h-12 -translate-y-1/2 bg-gradient-to-t from-[#7ae7ff] via-[#7ae7ff]/55 to-transparent shadow-[0_0_22px_rgba(122,231,255,0.95)]"
        initial={{ top: "100%", opacity: 1 }}
        animate={{ top: "0%", opacity: [1, 1, 0] }}
        transition={{
          duration: FORM_DURATION,
          delay: FORM_DELAY,
          ease: formEase,
          opacity: { duration: FORM_DURATION, delay: FORM_DELAY, times: [0, 0.88, 1] },
        }}
      />
    </div>
  );
}
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

      if (on && burstLeft > 0 && now - lastSpawn > 52) {
        lastSpawn = now;
        const n = Math.min(3, burstLeft);
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
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
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
