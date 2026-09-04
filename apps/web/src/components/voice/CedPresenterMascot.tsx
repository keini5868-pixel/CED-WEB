"use client";

import { motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  gestureForHotspot,
  gestureForModule,
  gestureForWorkspace,
  gesturePose,
  reactToSpeech,
  type PresenterGesture,
} from "@/lib/voice/presenterGestures";
import {
  isPresenterCloseSpeech,
  matchPresenterGuide,
  queryHotspot,
  runPresenterAction,
  clickElement,
  closeTargetHotspot,
  type GuideStep,
} from "@/lib/voice/presenterGuide";
import { CedHoloBotPuppet } from "@/components/voice/CedHoloBotPuppet";

type Props = {
  visible: boolean;
  exiting?: boolean;
  audioStream: MediaStream | null;
  workspace?: "chat" | "advanced" | "finance";
};

type Pose = { x: number; y: number; scale: number };

type Particle = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  max: number;
  size: number;
};

function homePose(): Pose {
  if (typeof window === "undefined") return { x: 420, y: 420, scale: 1 };
  return {
    x: window.innerWidth * 0.42,
    y: window.innerHeight * 0.54,
    scale: 1,
  };
}

function poseForEl(el: HTMLElement): Pose {
  const r = el.getBoundingClientRect();
  const header = r.top < 96;
  const sidebar = r.left > window.innerWidth * 0.62;
  if (header) {
    return {
      x: Math.min(window.innerWidth - 90, r.left + r.width * 0.5 + 52),
      y: Math.min(window.innerHeight * 0.42, r.bottom + 168),
      scale: 0.62,
    };
  }
  if (sidebar) {
    return {
      x: r.left - 28,
      y: r.top + r.height * 0.5 + 36,
      scale: 0.7,
    };
  }
  return {
    x: r.left + r.width * 0.5,
    y: r.top + r.height * 0.5 + 52,
    scale: 0.76,
  };
}

const POSE_TRANSITION =
  "left 0.72s cubic-bezier(0.16,1,0.3,1), top 0.72s cubic-bezier(0.16,1,0.3,1), transform 0.72s cubic-bezier(0.16,1,0.3,1)";

function writePose(node: HTMLElement | null, pose: Pose) {
  if (!node) return;
  node.style.left = `${Math.round(pose.x)}px`;
  node.style.top = `${Math.round(pose.y)}px`;
  node.style.transform = `translate(-50%, -78%) scale(${pose.scale})`;
}

function useStreamLevel(stream: MediaStream | null) {
  const levelRef = useRef(0);

  useEffect(() => {
    if (!stream) {
      levelRef.current = 0;
      return;
    }
    let raf = 0;
    let ctx: AudioContext | null = null;
    const AC =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return;
    ctx = new AC();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    const src = ctx.createMediaStreamSource(stream);
    src.connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) {
        const n = ((data[i] ?? 128) - 128) / 128;
        sum += n * n;
      }
      const rms = Math.min(1, Math.sqrt(sum / data.length) * 6);
      levelRef.current += (rms - levelRef.current) * 0.28;
      raf = requestAnimationFrame(tick);
    };
    void ctx.resume().then(() => {
      raf = requestAnimationFrame(tick);
    });
    return () => {
      cancelAnimationFrame(raf);
      void ctx?.close();
      levelRef.current = 0;
    };
  }, [stream]);

  return levelRef;
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

type SpeechRecLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((ev: {
    results: ArrayLike<ArrayLike<{ transcript?: string }> & { isFinal?: boolean }>;
  }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function spawnBurst(particles: Particle[], kind: PresenterGesture, w: number, h: number) {
  const n = kind === "success" || kind === "construct" ? 10 : kind === "error" ? 4 : 6;
  for (let i = 0; i < n; i += 1) {
    const ang = (Math.PI * 2 * i) / n + Math.random();
    const speed = kind === "construct" ? 1.6 : 2.4;
    particles.push({
      x: w * 0.5 + (Math.random() - 0.5) * 20,
      y: h * (kind === "think" ? 0.18 : 0.42),
      vx: Math.cos(ang) * speed,
      vy: Math.sin(ang) * speed - (kind === "success" ? 1.4 : 0.2),
      life: 1,
      max: 1,
      size: 1.4 + Math.random() * 2.2,
    });
    if (particles.length > 48) particles.shift();
  }
}

function paintCanvas(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  gesture: PresenterGesture,
  t: number,
  particles: Particle[],
) {
  ctx.clearRect(0, 0, w, h);
  const cx = w * 0.5;
  const cy = h * 0.46;

  if (gesture === "construct") {
    for (let i = 0; i < 3; i += 1) {
      const r = 28 + i * 16 + Math.sin(t * 3 + i) * 4;
      ctx.beginPath();
      ctx.ellipse(cx, cy + 8, r, r * 0.38, t * (1.2 + i * 0.4), 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(0,229,255,${0.35 - i * 0.08})`;
      ctx.lineWidth = 1.4;
      ctx.stroke();
    }
    const hx = cx + Math.cos(t * 4.2) * 42;
    const hy = cy + Math.sin(t * 3.4) * 18;
    ctx.beginPath();
    ctx.arc(hx, hy, 5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(180,255,255,0.85)";
    ctx.fill();
  }

  if (gesture === "think") {
    ctx.beginPath();
    ctx.arc(cx + 36, h * 0.14, 7 + Math.sin(t * 3) * 1.5, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(0,229,255,0.7)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cx + 48, h * 0.08, 3.2, 0, Math.PI * 2);
    ctx.stroke();
  }

  if (gesture === "listen") {
    for (let i = 0; i < 3; i += 1) {
      const a = (t * 1.8 + i * 0.7) % 1;
      ctx.beginPath();
      ctx.arc(cx + 40, cy - 20, 8 + a * 18, -0.6, 0.6);
      ctx.strokeStyle = `rgba(0,229,255,${0.45 * (1 - a)})`;
      ctx.lineWidth = 1.6;
      ctx.stroke();
    }
  }

  if (gesture === "point") {
    ctx.strokeStyle = "rgba(0,229,255,0.7)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(w * 0.7, h * 0.32);
    ctx.lineTo(w * 0.98, h * 0.08);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(w * 0.98, h * 0.08, 4, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(180,255,255,0.9)";
    ctx.fill();
  }

  for (let i = particles.length - 1; i >= 0; i -= 1) {
    const p = particles[i];
    if (!p) continue;
    p.x += p.vx;
    p.y += p.vy;
    p.vy += gesture === "success" ? -0.04 : 0.02;
    p.life -= 0.018;
    if (p.life <= 0) {
      particles.splice(i, 1);
      continue;
    }
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
    ctx.fillStyle =
      gesture === "error"
        ? `rgba(255,180,90,${0.7 * p.life})`
        : `rgba(0,229,255,${0.75 * p.life})`;
    ctx.fill();
  }
}

/** Holograma vivo: flota, gesticula y va a la pestaña de la que hablas. Sin TTS. */
export function CedPresenterMascot({
  visible,
  exiting = false,
  audioStream,
  workspace = "chat",
}: Props) {
  const levelRef = useStreamLevel(visible ? audioStream : null);
  const spriteRef = useRef<HTMLDivElement>(null);
  const scanRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const busyRef = useRef(false);
  const runGenRef = useRef(0);
  const lastKeyRef = useRef("");
  const lastAtRef = useRef(0);
  const poseRef = useRef<Pose>(homePose());
  const gestureRef = useRef<PresenterGesture>("idle");
  const particlesRef = useRef<Particle[]>([]);
  const [mounted, setMounted] = useState(false);
  const [pose, setPose] = useState<Pose>(() => homePose());
  const [gesture, setGesture] = useState<PresenterGesture>("idle");

  const applyPose = useCallback((next: Pose) => {
    poseRef.current = next;
    setPose(next);
    const node =
      wrapRef.current || document.querySelector<HTMLElement>("[data-ced-presenter-wrap]");
    writePose(node, next);
  }, []);

  const applyGesture = useCallback((next: PresenterGesture) => {
    gestureRef.current = next;
    setGesture(next);
    const canvas = canvasRef.current;
    if (canvas) {
      spawnBurst(particlesRef.current, next, canvas.width, canvas.height);
    }
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!visible) {
      applyPose(homePose());
      applyGesture("idle");
      return;
    }
    if (exiting) {
      applyGesture("farewell");
      applyPose(homePose());
      return;
    }
    applyGesture("welcome");
    const welcomeTimer = window.setTimeout(() => {
      if (gestureRef.current === "welcome") applyGesture("idle");
    }, 2600);
    return () => window.clearTimeout(welcomeTimer);
  }, [visible, exiting, applyPose, applyGesture]);

  useEffect(() => {
    if (!visible || exiting) return;
    const fromWs = gestureForWorkspace(workspace);
    if (fromWs) applyGesture(fromWs);
  }, [workspace, visible, exiting, applyGesture]);

  useEffect(() => {
    if (!visible || exiting) return;
    const onModule = (ev: Event) => {
      const mod = (ev as CustomEvent<{ module?: string | null }>).detail?.module;
      const next = gestureForModule(mod);
      if (next) applyGesture(next);
    };
    window.addEventListener("ced-module-active", onModule);
    return () => window.removeEventListener("ced-module-active", onModule);
  }, [visible, exiting, applyGesture]);

  useEffect(() => {
    if (!visible) return;
    let raf = 0;
    const t0 = performance.now();
    const loop = (now: number) => {
      const t = (now - t0) / 1000;
      const level = levelRef.current;
      const hearing = !exiting && !busyRef.current && level > 0.08;
      if (hearing && (gestureRef.current === "idle" || gestureRef.current === "listen")) {
        if (gestureRef.current !== "listen") {
          gestureRef.current = "listen";
          setGesture("listen");
        }
      } else if (!hearing && gestureRef.current === "listen") {
        gestureRef.current = "idle";
        setGesture("idle");
      }
      const g = gesturePose(gestureRef.current, t);
      const bob = (Math.sin(t * 1.7) * 8 + Math.sin(t * 0.9) * 3) * g.bobMul;
      const talk = hearing ? Math.sin(t * 11) * (5 + level * 14) : Math.sin(t * 2.4) * 2;
      const rotY = Math.sin(t * 1.05) * 10 + g.ry;
      const rotZ = Math.sin(t * 0.8) * 1.6 + g.rz;
      const rotX = Math.sin(t * 0.6) * 1.2 + g.rx;
      const scale = g.scale + level * 0.05;
      const flick = 0.88 + Math.sin(t * 31) * 0.07 + Math.sin(t * 8.5) * 0.05;
      const el = spriteRef.current;
      if (el) {
        el.style.transform = `translateY(${bob + talk + g.y}px) rotateX(${rotX}deg) rotateY(${rotY}deg) rotateZ(${rotZ}deg) scale(${scale})`;
        el.style.filter = `brightness(${flick}) contrast(1.08) drop-shadow(0 0 18px rgba(0,229,255,0.55))`;
      }
      const scan = scanRef.current;
      if (scan) scan.style.opacity = String(0.18 + level * 0.35);
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      if (canvas && ctx) {
        if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
          canvas.width = Math.max(1, canvas.clientWidth);
          canvas.height = Math.max(1, canvas.clientHeight);
        }
        if (gestureRef.current === "construct" && Math.random() < 0.18) {
          spawnBurst(particlesRef.current, "construct", canvas.width, canvas.height);
        }
        paintCanvas(ctx, canvas.width, canvas.height, gestureRef.current, t, particlesRef.current);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [visible, exiting, levelRef]);

  useEffect(() => {
    if (!visible || exiting) return;
    let cancelled = false;

    const isCloseSteps = (steps: GuideStep[]) =>
      steps.some((s) => Boolean(s.action) || s.force === "close");

    const runSteps = async (steps: GuideStep[]) => {
      const closing = isCloseSteps(steps);
      if (busyRef.current && !closing) return;
      const gen = ++runGenRef.current;
      busyRef.current = true;
      const stale = () => cancelled || gen !== runGenRef.current;
      const waitAlive = async (ms: number) => {
        const t0 = Date.now();
        while (Date.now() - t0 < ms) {
          if (stale()) return false;
          await wait(Math.min(40, ms - (Date.now() - t0)));
        }
        return !stale();
      };
      applyGesture(closing ? "ok" : gestureForHotspot(steps[0]?.hotspot || "sistema"));
      try {
        if (closing) {
          runPresenterAction("close-all");
          applyGesture("ok");
          const target = closeTargetHotspot();
          if (target) {
            target.classList.add("ced-presenter-focus");
            applyPose(poseForEl(target));
          } else {
            applyPose(homePose());
          }
          if (!(await waitAlive(700))) {
            target?.classList.remove("ced-presenter-focus");
            return;
          }
          target?.classList.remove("ced-presenter-focus");
          if (!exiting) {
            applyGesture("ok");
            applyPose(homePose());
          }
          return;
        }

        for (const step of steps) {
          if (stale()) return;
          if (step.action) {
            applyGesture("ok");
            applyPose(homePose());
            runPresenterAction(step.action);
            if (!(await waitAlive(180))) return;
            continue;
          }
          if (!step.hotspot) continue;
          let el: HTMLElement | null = null;
          for (let i = 0; i < 16 && !el; i += 1) {
            if (stale()) return;
            el = queryHotspot(step.hotspot);
            if (!el) await wait(50);
          }
          if (!el) continue;
          applyGesture(gestureForHotspot(step.hotspot));
          el.classList.add("ced-presenter-focus");
          applyPose(poseForEl(el));
          if (!(await waitAlive(480))) {
            el.classList.remove("ced-presenter-focus");
            return;
          }
          if (step.click) {
            const wrap = wrapRef.current;
            const scale = poseRef.current.scale;
            if (wrap) {
              wrap.style.transform = `translate(-50%, -78%) scale(${scale * 0.86})`;
              if (!(await waitAlive(120))) {
                el.classList.remove("ced-presenter-focus");
                return;
              }
              wrap.style.transform = `translate(-50%, -78%) scale(${scale})`;
              if (!(await waitAlive(70))) {
                el.classList.remove("ced-presenter-focus");
                return;
              }
            }
            if (stale()) {
              el.classList.remove("ced-presenter-focus");
              return;
            }
            const expanded =
              el.getAttribute("aria-expanded") ?? el.getAttribute("data-ced-open");
            if (!(step.force === "open" && expanded === "true")) {
              clickElement(el);
            }
          }
          if (!(await waitAlive(480))) {
            el.classList.remove("ced-presenter-focus");
            return;
          }
          el.classList.remove("ced-presenter-focus");
        }
        if (stale()) return;
        applyGesture("ok");
        if (!(await waitAlive(1600))) return;
        if (!exiting) {
          applyGesture("idle");
          applyPose(homePose());
        }
      } finally {
        if (gen === runGenRef.current) busyRef.current = false;
      }
    };

    const onSpeech = (raw: string) => {
      const felt = reactToSpeech(raw);
      if (felt) applyGesture(felt);
      const steps = matchPresenterGuide(raw);
      if (!steps) return;
      if (isPresenterCloseSpeech(raw) || isCloseSteps(steps)) {
        applyGesture("ok");
        runPresenterAction("close-all");
      }
      const key = steps
        .map((s) => s.action || `${s.force || "go"}:${s.hotspot || ""}`)
        .join(">");
      const now = Date.now();
      const closing = isCloseSteps(steps);
      if (!closing && key === lastKeyRef.current && now - lastAtRef.current < 4500) return;
      if (closing && key === lastKeyRef.current && now - lastAtRef.current < 900) return;
      lastKeyRef.current = key;
      lastAtRef.current = now;
      void runSteps(steps);
    };

    const onSay = (ev: Event) => {
      const text = (ev as CustomEvent<string>).detail;
      if (typeof text === "string") onSpeech(text);
    };
    window.addEventListener("ced-presenter-say", onSay);

    const SpeechRec =
      (window as unknown as { SpeechRecognition?: new () => SpeechRecLike }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecLike }).webkitSpeechRecognition;
    let rec: SpeechRecLike | null = null;
    if (SpeechRec) {
      rec = new SpeechRec();
      rec.lang = "es-ES";
      rec.continuous = true;
      rec.interimResults = true;
      rec.onresult = (ev) => {
        const list = ev.results;
        const row = list[list.length - 1];
        const text = (row?.[0]?.transcript || "").trim();
        const isFinal = row && (row as { isFinal?: boolean }).isFinal !== false;
        if (isPresenterCloseSpeech(text)) {
          onSpeech(text);
          return;
        }
        if (!text || text.length < 4) return;
        if (!isFinal && text.length < 10) return;
        onSpeech(text);
      };
      rec.onend = () => {
        if (!cancelled) {
          try {
            rec?.start();
          } catch {
            /* already started */
          }
        }
      };
      try {
        rec.start();
      } catch {
        /* permission / unsupported */
      }
    }
    return () => {
      cancelled = true;
      window.removeEventListener("ced-presenter-say", onSay);
      if (!rec) return;
      rec.onend = null;
      rec.onresult = null;
      try {
        rec.stop();
      } catch {
        /* ignore */
      }
    };
  }, [visible, exiting, applyPose, applyGesture]);

  if (!mounted) return null;

  return createPortal(
    <div className="pointer-events-none fixed inset-0 z-[220]" aria-hidden>
      {visible ? (
        <div
          ref={wrapRef}
          data-ced-presenter-wrap
          data-ced-gesture={gesture}
          className="absolute will-change-[left,top,transform]"
          style={{
            left: `${pose.x}px`,
            top: `${pose.y}px`,
            transform: `translate(-50%, -78%) scale(${pose.scale})`,
            transition: POSE_TRANSITION,
            perspective: 720,
            opacity: exiting ? 0.15 : 1,
          }}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.45, filter: "blur(10px)" }}
            animate={{
              opacity: exiting ? 0 : 1,
              scale: exiting ? 0.55 : 1,
              filter: exiting ? "blur(12px)" : "blur(0px)",
            }}
            transition={{ duration: exiting ? 0.65 : 0.45, ease: [0.16, 1, 0.3, 1] }}
          >
            <div
              ref={spriteRef}
              className="relative will-change-transform"
              style={{ transformStyle: "preserve-3d" }}
            >
              <CedHoloBotPuppet gesture={gesture} />
              <canvas
                ref={canvasRef}
                className="pointer-events-none absolute inset-0 h-full w-full"
              />
            </div>
          </motion.div>
        </div>
      ) : null}
    </div>,
    document.body,
  );
}
