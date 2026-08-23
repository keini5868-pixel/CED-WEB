"use client";

import { useEffect, useRef, useState, type MutableRefObject } from "react";
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
  nx: number;
  ny: number;
  t: number;
  speed: number;
  amp: number;
  phase: number;
  size: number;
  life: number;
};

type Stamp = { nx: number; ny: number; r: number };

type Pt = { x: number; y: number };

const HOLO_SRC = "/voice/holo-presence.png?v=mesh5";
const FILL_MS = 2400;

function spawnSpark(
  ox: number,
  oy: number,
  tx: number,
  ty: number,
  nx: number,
  ny: number,
): Spark {
  return {
    x: ox + (Math.random() - 0.5) * 8,
    y: oy + (Math.random() - 0.5) * 8,
    tx,
    ty,
    nx,
    ny,
    t: 0,
    speed: 0.007 + Math.random() * 0.006,
    amp: 8 + Math.random() * 18,
    phase: Math.random() * Math.PI * 2,
    size: 1.8 + Math.random() * 2.4,
    life: 1,
  };
}

function sampleSilhouette(img: HTMLImageElement): Pt[] {
  const c = document.createElement("canvas");
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  c.width = w;
  c.height = h;
  const g = c.getContext("2d");
  if (!g) return [];
  g.drawImage(img, 0, 0);
  const data = g.getImageData(0, 0, w, h).data;
  const raw: Pt[] = [];
  const step = 5;
  for (let y = 0; y < h; y += step) {
    for (let x = 0; x < w; x += step) {
      const alpha = data[(y * w + x) * 4 + 3] ?? 0;
      if (alpha > 48) {
        raw.push({ x: x / w, y: y / h });
      }
    }
  }
  raw.sort((a, b) => b.y - a.y);
  const n = 320;
  if (raw.length <= n) return raw;
  const out: Pt[] = [];
  for (let i = 0; i < n; i += 1) {
    const pt = raw[Math.floor((i / n) * raw.length)];
    if (pt) out.push(pt);
  }
  return out;
}

function HoloFace({
  speaking,
  active,
  stampsRef,
  fillDone,
}: {
  speaking: boolean;
  active: boolean;
  stampsRef: MutableRefObject<Stamp[]>;
  fillDone: boolean;
}) {
  const visRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const maskRef = useRef<HTMLCanvasElement | null>(null);
  const stampedRef = useRef(0);
  const fillDoneRef = useRef(fillDone);
  fillDoneRef.current = fillDone;
  const ringSpeed = speaking ? 1.35 : 2.8;
  const spinSpeed = speaking ? 9 : 22;
  const talk = speaking && fillDone;

  useEffect(() => {
    const vis = visRef.current;
    const wrap = wrapRef.current;
    if (!vis || !wrap) return;
    const ctx = vis.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.src = HOLO_SRC;
    imgRef.current = img;

    const mask = document.createElement("canvas");
    maskRef.current = mask;
    const mctx = mask.getContext("2d");
    if (!mctx) return;

    let raf = 0;
    const resize = () => {
      const r = wrap.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      vis.width = Math.max(1, Math.floor(r.width * dpr));
      vis.height = Math.max(1, Math.floor(r.height * dpr));
      vis.style.width = `${r.width}px`;
      vis.style.height = `${r.height}px`;
      mask.width = vis.width;
      mask.height = vis.height;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      mctx.setTransform(1, 0, 0, 1, 0, 0);
      stampedRef.current = 0;
    };

    const tick = () => {
      const r = wrap.getBoundingClientRect();
      const w = vis.width;
      const h = vis.height;
      if (!w || !h) {
        raf = requestAnimationFrame(tick);
        return;
      }

      const stamps = stampsRef.current;
      if (stamps.length < stampedRef.current) {
        mctx.clearRect(0, 0, w, h);
        stampedRef.current = 0;
      }
      for (let i = stampedRef.current; i < stamps.length; i += 1) {
        const s = stamps[i];
        if (!s) continue;
        const x = s.nx * w;
        const y = s.ny * h;
        const rad = s.r * (w / Math.max(r.width, 1));
        const g = mctx.createRadialGradient(x, y, 0, x, y, rad);
        g.addColorStop(0, "rgba(255,255,255,1)");
        g.addColorStop(0.55, "rgba(255,255,255,0.85)");
        g.addColorStop(1, "rgba(255,255,255,0)");
        mctx.fillStyle = g;
        mctx.beginPath();
        mctx.arc(x, y, rad, 0, Math.PI * 2);
        mctx.fill();
      }
      stampedRef.current = stamps.length;

      ctx.clearRect(0, 0, w, h);
      if (img.complete && img.naturalWidth) {
        ctx.drawImage(img, 0, 0, w, h);
        if (!fillDoneRef.current) {
          ctx.globalCompositeOperation = "destination-in";
          ctx.drawImage(mask, 0, 0);
          ctx.globalCompositeOperation = "source-over";
        }
      }
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
  }, [stampsRef]);

  useEffect(() => {
    if (!active) stampedRef.current = 0;
  }, [active]);

  return (
    <motion.div
      ref={wrapRef}
      className="relative w-[min(78vw,19rem)] sm:w-[21rem] lg:w-[24rem]"
      animate={
        talk
          ? {
              rotate: [-1.6, 1.4, -0.9, 1.7, -1.6],
              y: [0, -5, 2, -3, 0],
              scale: [1, 1.018, 0.992, 1.012, 1],
            }
          : fillDone
            ? { rotate: [-0.35, 0.35, -0.35], y: [0, -1.5, 0], scale: 1 }
            : { rotate: 0, y: 0, scale: 1 }
      }
      transition={{
        duration: talk ? 2.8 : 5.5,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    >
      <div className="absolute inset-[16%] rounded-full bg-[#4fd4ee]/18 blur-3xl" />
      <img src={HOLO_SRC} alt="" className="pointer-events-none w-full opacity-0" />
      <canvas ref={visRef} className="absolute inset-0 h-full w-full" />

      {fillDone ? (
        <>
          {[0, 1, 2, 3].map((i) => (
            <motion.div
              key={`echo-${i}`}
              className="absolute left-1/2 top-[46%] z-0 h-[70%] w-[58%] -translate-x-1/2 -translate-y-1/2 rounded-[46%] border border-[#7ae7ff]/45"
              initial={{ scale: 1, opacity: 0.5 }}
              animate={{ scale: [1, 1.28], opacity: [0.5, 0] }}
              transition={{
                duration: ringSpeed,
                delay: i * (ringSpeed / 4),
                repeat: Infinity,
                ease: "easeOut",
              }}
            />
          ))}
          <motion.div
            className="absolute left-[8%] right-[8%] top-[4%] bottom-[14%] z-0 rounded-[46%] border border-dashed border-[#4fd4ee]/55"
            animate={{ rotate: 360 }}
            transition={{ duration: spinSpeed, repeat: Infinity, ease: "linear" }}
          />
          <motion.div
            className="absolute left-[16%] right-[16%] top-[10%] bottom-[20%] z-0 rounded-[46%] border border-dotted border-[#7ae7ff]/40"
            animate={{ rotate: -360 }}
            transition={{ duration: spinSpeed * 1.35, repeat: Infinity, ease: "linear" }}
          />
        </>
      ) : null}

      <motion.div
        className="absolute left-1/2 top-[88%] z-[4] -translate-x-1/2 -translate-y-1/2"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.55, duration: 0.45 }}
      >
        <motion.svg
          viewBox="0 0 64 78"
          className="h-11 w-11 drop-shadow-[0_0_10px_rgba(122,231,255,0.95)] sm:h-12 sm:w-12"
          animate={{ opacity: [0.85, 1, 0.85], scale: [1, 1.06, 1] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
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
      </motion.div>

      {fillDone ? (
        <>
          {(
            [
              { side: "left" as const, x: "38.5%" },
              { side: "right" as const, x: "61.5%" },
            ]
          ).map((eye) => (
            <motion.div
              key={`brow-${eye.side}`}
              className="absolute z-[3] h-[2px] w-[12%] -translate-x-1/2 rounded-full bg-[#e8fbff]/80 shadow-[0_0_8px_#7ae7ff]"
              style={{ left: eye.x, top: "39%" }}
              animate={
                talk
                  ? {
                      y: [0, -4, -1, -5, 0],
                      rotate: eye.side === "left" ? [-6, 4, -8, 2] : [6, -4, 8, -2],
                      opacity: [0.45, 0.9, 0.5, 0.85],
                    }
                  : { y: [0, -1, 0], opacity: [0.25, 0.4, 0.25] }
              }
              transition={{ duration: talk ? 2.2 : 4, repeat: Infinity, ease: "easeInOut" }}
            />
          ))}
          {["38.5%", "61.5%"].map((x) => (
            <motion.div
              key={`eye-${x}`}
              className="absolute z-[3] h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#7ae7ff]/35 shadow-[0_0_12px_#4fd4ee]"
              style={{ left: x, top: "44.5%" }}
              animate={
                talk
                  ? {
                      scaleY: [1, 1, 0.12, 1, 1, 1, 0.12, 1],
                      scaleX: [1, 1.08, 1, 0.95, 1.1],
                      opacity: [0.5, 0.85, 0.2, 0.8],
                    }
                  : { scaleY: [1, 1, 0.15, 1], opacity: [0.3, 0.45, 0.3] }
              }
              transition={{
                duration: talk ? 3.4 : 5.2,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />
          ))}
        </>
      ) : null}

      {speaking
        ? [0, 1, 2].map((i) => (
            <motion.div
              key={`voice-${i}`}
              className="absolute left-1/2 top-[63.5%] z-[3] h-2.5 w-11 -translate-x-1/2 -translate-y-1/2 rounded-[999px] border border-[#7ae7ff]/80 shadow-[0_0_10px_rgba(122,231,255,0.55)] sm:h-3 sm:w-12"
              initial={{ scaleX: 0.75, scaleY: 0.55, opacity: 0.85 }}
              animate={{
                scaleX: [0.7, 1.45, 0.85, 1.3],
                scaleY: [0.5, 1.55, 0.7, 1.25],
                opacity: [0.85, 0],
              }}
              transition={{
                duration: 0.48,
                delay: i * 0.14,
                repeat: Infinity,
                ease: "easeOut",
              }}
            />
          ))
        : null}
    </motion.div>
  );
}

/** Partículas desde ESCUCHAR rellenan el rostro de abajo hacia arriba. */
export function CedHoloPresence({ active, speaking }: CedHoloPresenceProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const faceRef = useRef<HTMLDivElement>(null);
  const sparksRef = useRef<Spark[]>([]);
  const stampsRef = useRef<Stamp[]>([]);
  const pointsRef = useRef<Pt[]>([]);
  const idxRef = useRef(0);
  const activeRef = useRef(active);
  const fillDoneRef = useRef(false);
  const [fillDone, setFillDone] = useState(false);

  useEffect(() => {
    activeRef.current = active;
    if (!active) {
      stampsRef.current = [];
      idxRef.current = 0;
      sparksRef.current = [];
      fillDoneRef.current = false;
      setFillDone(false);
    }
  }, [active]);

  useEffect(() => {
    const img = new Image();
    img.src = HOLO_SRC;
    img.onload = () => {
      pointsRef.current = sampleSilhouette(img);
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let lastSpawn = 0;
    let startedAt = 0;
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

    const faceTarget = (pt: Pt) => {
      const root = wrap.getBoundingClientRect();
      const face = faceRef.current?.getBoundingClientRect();
      if (!face) {
        return { tx: root.width * 0.38, ty: root.height * 0.55, nx: pt.x, ny: pt.y };
      }
      return {
        tx: face.left - root.left + pt.x * face.width,
        ty: face.top - root.top + pt.y * face.height,
        nx: pt.x,
        ny: pt.y,
      };
    };

    const tick = (now: number) => {
      const r = wrap.getBoundingClientRect();
      ctx.clearRect(0, 0, r.width, r.height);
      const on = activeRef.current;
      const btn = document.querySelector<HTMLElement>("[data-ced-listen]");
      const ox = btn ? btn.getBoundingClientRect().left + btn.offsetWidth / 2 - wrap.getBoundingClientRect().left : r.width - 48;
      const oy = btn ? btn.getBoundingClientRect().top + btn.offsetHeight / 2 - wrap.getBoundingClientRect().top : r.height * 0.62;

      if (!on) {
        armed = true;
        startedAt = 0;
      } else if (armed) {
        armed = false;
        startedAt = now;
        idxRef.current = 0;
        stampsRef.current = [];
      }

      const pts = pointsRef.current;
      const filling = on && startedAt > 0 && now - startedAt < FILL_MS + 900;
      if (filling && now - lastSpawn > 38 && idxRef.current < pts.length) {
        lastSpawn = now;
        const n = Math.min(6, pts.length - idxRef.current);
        for (let i = 0; i < n; i += 1) {
          const pt = pts[idxRef.current];
          idxRef.current += 1;
          if (!pt) continue;
          const t = faceTarget(pt);
          sparksRef.current.push(spawnSpark(ox, oy, t.tx, t.ty, t.nx, t.ny));
        }
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
        if (u >= 1) {
          stampsRef.current.push({ nx: p.nx, ny: p.ny, r: 18 + Math.random() * 10 });
          continue;
        }
        p.life = on ? 1 - u : p.life - 0.06;
        if (p.life <= 0) continue;
        next.push(p);
        ctx.beginPath();
        ctx.fillStyle = `rgba(180, 245, 255, ${0.5 + p.life * 0.5})`;
        ctx.shadowColor = "#7ae7ff";
        ctx.shadowBlur = 14;
        ctx.arc(x, y, p.size + 0.8, 0, Math.PI * 2);
        ctx.fill();
      }
      sparksRef.current = next;
      ctx.shadowBlur = 0;

      if (on && startedAt > 0 && now - startedAt > FILL_MS && next.length === 0) {
        if (!fillDoneRef.current) {
          fillDoneRef.current = true;
          setFillDone(true);
        }
      }
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
              <HoloFace speaking={speaking} active={active} stampsRef={stampsRef} fillDone={fillDone} />
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}
