"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "framer-motion";

type Flourish = "none" | "wave" | "point-left" | "point-right";

export type CedPresenterMascotHandle = {
  releaseMic: () => void;
};

type Props = {
  /** Visible mientras el presentador está encendido y el asistente NO está activo. */
  visible: boolean;
};

function usePresenterVoiceLevel(enabled: boolean) {
  const [level, setLevel] = useState(0);
  const stopRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!enabled || typeof navigator === "undefined") {
      setLevel(0);
      return;
    }

    let stopped = false;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    let raf = 0;
    let started = false;

    const teardown = () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
      stream = null;
      void ctx?.close();
      ctx = null;
      setLevel(0);
    };
    stopRef.current = teardown;

    const start = async () => {
      if (started || stopped) return;
      if (!navigator.mediaDevices?.getUserMedia) return;
      started = true;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
          video: false,
        });
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        const AC =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext?: typeof AudioContext })
            .webkitAudioContext;
        if (!AC) return;
        ctx = new AC();
        if (ctx.state === "suspended") {
          await ctx.resume();
        }
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        src.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);
        const tick = () => {
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i += 1) {
            const n = ((data[i] ?? 128) - 128) / 128;
            sum += n * n;
          }
          const rms = Math.sqrt(sum / data.length);
          setLevel(Math.min(1, rms * 5.2));
          raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      } catch {
        started = false;
      }
    };

    const onGesture = () => {
      void start();
    };
    window.addEventListener("pointerdown", onGesture);

    return () => {
      window.removeEventListener("pointerdown", onGesture);
      teardown();
      stopRef.current = () => {};
    };
  }, [enabled]);

  return {
    level,
    releaseMic: () => {
      stopRef.current();
    },
  };
}

const PARTICLES = [
  { cx: 18, cy: 42, r: 1.1, d: 2.4 },
  { cx: 86, cy: 28, r: 0.9, d: 3.1 },
  { cx: 22, cy: 88, r: 1.2, d: 2.8 },
  { cx: 84, cy: 96, r: 0.8, d: 2.2 },
  { cx: 50, cy: 14, r: 1, d: 3.4 },
  { cx: 12, cy: 64, r: 0.7, d: 2.6 },
  { cx: 92, cy: 58, r: 1, d: 2.9 },
];

/** Mini holograma chibi — mismo look que la referencia de taller. */
export const CedPresenterMascot = forwardRef<CedPresenterMascotHandle, Props>(
  function CedPresenterMascot({ visible }, ref) {
    const { level, releaseMic } = usePresenterVoiceLevel(visible);
    const talking = visible && level > 0.1;
    const [flourish, setFlourish] = useState<Flourish>("none");

    useImperativeHandle(ref, () => ({ releaseMic }), [releaseMic]);

    useEffect(() => {
      if (!visible) {
        setFlourish("none");
        return;
      }
      const id = window.setInterval(() => {
        const pick: Flourish = talking
          ? Math.random() > 0.5
            ? "point-left"
            : "point-right"
          : Math.random() > 0.45
            ? "wave"
            : "none";
        setFlourish(pick);
        window.setTimeout(() => setFlourish("none"), 1100);
      }, 3000);
      return () => window.clearInterval(id);
    }, [visible, talking]);

    const leftArm =
      flourish === "wave"
        ? { rotate: [-8, -54, -12, -48, -8] }
        : flourish === "point-left"
          ? { rotate: [-10, -78, -72, -10] }
          : talking
            ? { rotate: [-8, 10, -6, 8, -8] }
            : { rotate: [-5, 6, -5] };

    const rightArm =
      flourish === "point-right"
        ? { rotate: [10, 78, 72, 10] }
        : talking
          ? { rotate: [8, -10, 6, -8, 8] }
          : { rotate: [5, -6, 5] };

    const mouthH = 1.6 + level * 5.5;

    return (
      <div
        className="pointer-events-none absolute inset-0 z-[79] flex items-center justify-center overflow-hidden pr-[6.5rem] sm:pr-[8rem] lg:pr-[min(15.5rem,28vw)]"
        aria-hidden
      >
        <AnimatePresence>
          {visible ? (
            <motion.div
              key="ced-presenter"
              className="relative translate-y-[8%]"
              initial={{ opacity: 0, y: 10, scale: 0.86 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.9, filter: "blur(6px)" }}
              transition={{ duration: 0.32, ease: "easeOut" }}
            >
              <motion.div
                animate={{
                  y: talking ? [0, -3, -1, -2.5, 0] : [0, -2.5, 0],
                  opacity: [0.92, 1, 0.88, 1],
                }}
                transition={{
                  y: {
                    duration: talking ? 0.48 : 3.8,
                    repeat: Infinity,
                    ease: "easeInOut",
                  },
                  opacity: { duration: 2.6, repeat: Infinity, ease: "easeInOut" },
                }}
                className="relative"
              >
                <svg
                  viewBox="0 0 100 148"
                  className="h-[8.75rem] w-auto drop-shadow-[0_0_18px_rgba(0,229,255,0.7)] sm:h-[10.25rem] lg:h-[11.5rem]"
                >
                  <defs>
                    <linearGradient id="ced-bot-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f2ffff" stopOpacity="0.82" />
                      <stop offset="45%" stopColor="#00e5ff" stopOpacity="0.55" />
                      <stop offset="100%" stopColor="#0090a3" stopOpacity="0.28" />
                    </linearGradient>
                    <pattern
                      id="ced-bot-grid"
                      width="5"
                      height="5"
                      patternUnits="userSpaceOnUse"
                    >
                      <path
                        d="M5 0 H0 V5"
                        fill="none"
                        stroke="#7ae7ff"
                        strokeWidth="0.35"
                        opacity="0.55"
                      />
                    </pattern>
                    <radialGradient id="ced-bot-beam" cx="50%" cy="0%" r="80%">
                      <stop offset="0%" stopColor="#00e5ff" stopOpacity="0.5" />
                      <stop offset="100%" stopColor="#00e5ff" stopOpacity="0" />
                    </radialGradient>
                    <filter id="ced-bot-glow" x="-40%" y="-40%" width="180%" height="180%">
                      <feGaussianBlur stdDeviation="1.4" result="b" />
                      <feMerge>
                        <feMergeNode in="b" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                    <clipPath id="ced-bot-scan-clip">
                      <rect x="18" y="8" width="64" height="108" rx="16" />
                    </clipPath>
                  </defs>

                  {PARTICLES.map((p) => (
                    <motion.circle
                      key={`${p.cx}-${p.cy}`}
                      cx={p.cx}
                      cy={p.cy}
                      r={p.r}
                      fill="#9ff6ff"
                      animate={{
                        cy: [p.cy, p.cy - 6, p.cy],
                        opacity: [0.15, 0.85, 0.15],
                      }}
                      transition={{ duration: p.d, repeat: Infinity, ease: "easeInOut" }}
                    />
                  ))}

                  <ellipse cx="50" cy="140" rx="22" ry="3.4" fill="#00e5ff" opacity="0.22" />
                  <rect x="32" y="132" width="36" height="10" rx="2.2" fill="#0a1418" stroke="#3ec8dc" strokeWidth="0.9" />
                  <rect x="34" y="139" width="32" height="1.4" rx="0.7" fill="#00e5ff" opacity="0.75" />
                  <circle cx="50" cy="132" r="3.2" fill="#00e5ff" opacity="0.55" />
                  <text
                    x="50"
                    y="139"
                    textAnchor="middle"
                    fill="#7ae7ff"
                    fontSize="3.4"
                    fontFamily="var(--font-orbitron), sans-serif"
                    letterSpacing="0.4"
                  >
                    HOLO-BOT
                  </text>
                  <polygon points="44,118 56,118 62,132 38,132" fill="url(#ced-bot-beam)" />

                  <g filter="url(#ced-bot-glow)">
                    <motion.g
                      style={{ transformOrigin: "32px 78px", transformBox: "fill-box" }}
                      animate={leftArm}
                      transition={{
                        duration: flourish === "wave" ? 0.62 : 0.9,
                        repeat: Infinity,
                        ease: "easeInOut",
                      }}
                    >
                      <rect x="27" y="76" width="7" height="18" rx="3" fill="url(#ced-bot-fill)" stroke="#7ae7ff" strokeWidth="0.9" />
                      <rect x="27" y="76" width="7" height="18" rx="3" fill="url(#ced-bot-grid)" opacity="0.45" />
                      <circle cx="30.5" y="95" r="3.4" fill="#b8f6ff" opacity="0.55" stroke="#7ae7ff" strokeWidth="0.6" />
                      <path d="M27 97 h2.2 v4 H27 z M30 97 h2.2 v4.6 H30 z M33 97 h2 v3.6 H33 z" fill="#9ff6ff" opacity="0.8" />
                    </motion.g>
                    <motion.g
                      style={{ transformOrigin: "68px 78px", transformBox: "fill-box" }}
                      animate={rightArm}
                      transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut" }}
                    >
                      <rect x="66" y="76" width="7" height="18" rx="3" fill="url(#ced-bot-fill)" stroke="#7ae7ff" strokeWidth="0.9" />
                      <rect x="66" y="76" width="7" height="18" rx="3" fill="url(#ced-bot-grid)" opacity="0.45" />
                      <circle cx="69.5" y="95" r="3.4" fill="#b8f6ff" opacity="0.55" stroke="#7ae7ff" strokeWidth="0.6" />
                      <path d="M66 97 h2 v3.6 H66 z M69 97 h2.2 v4.6 H69 z M72.2 97 h2.2 v4 H72.2 z" fill="#9ff6ff" opacity="0.8" />
                    </motion.g>

                    <rect x="40" y="96" width="8" height="16" rx="2.4" fill="url(#ced-bot-fill)" stroke="#7ae7ff" strokeWidth="0.85" />
                    <rect x="52" y="96" width="8" height="16" rx="2.4" fill="url(#ced-bot-fill)" stroke="#7ae7ff" strokeWidth="0.85" />
                    <rect x="40" y="96" width="8" height="16" rx="2.4" fill="url(#ced-bot-grid)" opacity="0.4" />
                    <rect x="52" y="96" width="8" height="16" rx="2.4" fill="url(#ced-bot-grid)" opacity="0.4" />
                    <rect x="38.5" y="110" width="11" height="4.2" rx="1.2" fill="#c8fbff" opacity="0.55" stroke="#7ae7ff" strokeWidth="0.5" />
                    <rect x="50.5" y="110" width="11" height="4.2" rx="1.2" fill="#c8fbff" opacity="0.55" stroke="#7ae7ff" strokeWidth="0.5" />

                    <rect
                      x="36"
                      y="68"
                      width="28"
                      height="30"
                      rx="5"
                      fill="url(#ced-bot-fill)"
                      stroke="#9ff6ff"
                      strokeWidth="1.15"
                    />
                    <rect x="36" y="68" width="28" height="30" rx="5" fill="url(#ced-bot-grid)" opacity="0.5" />
                    <rect x="41" y="78" width="18" height="11" rx="2" fill="#041018" stroke="#e8fbff" strokeWidth="0.7" />
                    <text
                      x="50"
                      y="86.5"
                      textAnchor="middle"
                      fill="#e8fbff"
                      fontSize="6.2"
                      fontWeight="700"
                      fontFamily="var(--font-orbitron), sans-serif"
                      letterSpacing="0.8"
                    >
                      CED
                    </text>

                    <circle cx="50" cy="44" r="20" fill="url(#ced-bot-fill)" stroke="#b8f6ff" strokeWidth="1.35" />
                    <circle cx="50" cy="44" r="20" fill="url(#ced-bot-grid)" opacity="0.45" />
                    <rect x="28.5" y="38" width="5" height="11" rx="2.2" fill="#9ff6ff" opacity="0.85" />
                    <rect x="66.5" y="38" width="5" height="11" rx="2.2" fill="#9ff6ff" opacity="0.85" />
                    <circle cx="42.5" cy="43" r="5.2" fill="#041018" stroke="#e8fbff" strokeWidth="0.85" />
                    <circle cx="57.5" cy="43" r="5.2" fill="#041018" stroke="#e8fbff" strokeWidth="0.85" />
                    <motion.circle
                      cx="43.4"
                      cy="42.2"
                      r="2"
                      fill="#7ae7ff"
                      animate={{ opacity: talking ? [1, 0.4, 1] : [0.8, 1, 0.8] }}
                      transition={{ duration: talking ? 0.26 : 2.2, repeat: Infinity }}
                    />
                    <motion.circle
                      cx="58.4"
                      cy="42.2"
                      r="2"
                      fill="#7ae7ff"
                      animate={{ opacity: talking ? [1, 0.4, 1] : [0.8, 1, 0.8] }}
                      transition={{ duration: talking ? 0.26 : 2.2, repeat: Infinity }}
                    />
                    <ellipse
                      cx="50"
                      cy="54.5"
                      rx="5.4"
                      ry={mouthH}
                      fill="#041018"
                      stroke="#7ae7ff"
                      strokeWidth="0.7"
                    />
                  </g>

                  <g clipPath="url(#ced-bot-scan-clip)" opacity="0.28">
                    <motion.rect
                      x="18"
                      width="64"
                      height="10"
                      fill="url(#ced-bot-beam)"
                      animate={{ y: [12, 108] }}
                      transition={{ duration: 2.8, repeat: Infinity, ease: "linear" }}
                    />
                  </g>
                </svg>
              </motion.div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    );
  },
);
