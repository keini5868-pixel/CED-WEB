"use client";

import { useEffect, useRef } from "react";

import {
  gestureRig,
  type HandShape,
  type PresenterGesture,
} from "@/lib/voice/presenterGestures";

type Props = {
  gesture: PresenterGesture;
};

function mouthPath(kind: ReturnType<typeof gestureRig>["mouth"]): string {
  switch (kind) {
    case "grin":
      return "M 84 76 Q 100 100 116 76";
    case "oh":
      return "M 94 74 Q 100 90 106 74";
    case "flat":
      return "M 88 80 L 112 80";
    case "sad":
      return "M 86 86 Q 100 76 114 86";
    default:
      return "M 88 78 Q 100 92 112 78";
  }
}

function setHand(group: SVGGElement | null, kind: HandShape) {
  if (!group) return;
  for (const node of Array.from(group.children)) {
    const el = node as SVGElement;
    el.setAttribute("opacity", el.getAttribute("data-hand") === kind ? "1" : "0");
  }
}

function HandShapes() {
  return (
    <>
      <g data-hand="fingers">
        <circle cx="0" cy="42" r="8" fill="#b8ffff" fillOpacity="0.55" />
        <line x1="-8" y1="48" x2="-12" y2="62" strokeWidth="2.8" />
        <line x1="0" y1="50" x2="0" y2="64" strokeWidth="2.8" />
        <line x1="8" y1="48" x2="12" y2="62" strokeWidth="2.8" />
      </g>
      <g data-hand="palm" opacity="0">
        <ellipse cx="0" cy="50" rx="13" ry="16" fill="#b8ffff" fillOpacity="0.45" />
        <ellipse cx="0" cy="50" rx="13" ry="16" fill="none" />
        <line x1="-9" y1="58" x2="-11" y2="70" strokeWidth="2.4" />
        <line x1="-3" y1="62" x2="-4" y2="74" strokeWidth="2.4" />
        <line x1="3" y1="62" x2="4" y2="74" strokeWidth="2.4" />
        <line x1="9" y1="58" x2="11" y2="70" strokeWidth="2.4" />
      </g>
      <g data-hand="thumb" opacity="0">
        <ellipse cx="0" cy="46" rx="9" ry="12" fill="#b8ffff" fillOpacity="0.5" />
        <ellipse cx="0" cy="46" rx="9" ry="12" fill="none" />
        <line x1="7" y1="38" x2="16" y2="18" strokeWidth="4.2" strokeLinecap="round" />
        <circle cx="16" cy="16" r="3.6" fill="#d6ffff" fillOpacity="0.8" stroke="#9ffffa" />
      </g>
      <g data-hand="cup" opacity="0">
        <ellipse cx="2" cy="46" rx="11" ry="9" fill="#b8ffff" fillOpacity="0.5" />
        <ellipse cx="2" cy="46" rx="11" ry="9" fill="none" />
      </g>
    </>
  );
}

/** Holograma articulado al estilo de las 5 poses de referencia. */
export function CedHoloBotPuppet({ gesture }: Props) {
  const lArmRef = useRef<SVGGElement>(null);
  const lForeRef = useRef<SVGGElement>(null);
  const lHandRef = useRef<SVGGElement>(null);
  const rArmRef = useRef<SVGGElement>(null);
  const rForeRef = useRef<SVGGElement>(null);
  const rHandRef = useRef<SVGGElement>(null);
  const headRef = useRef<SVGGElement>(null);
  const eyesOpenRef = useRef<SVGGElement>(null);
  const eyesHappyRef = useRef<SVGGElement>(null);
  const eyesSadRef = useRef<SVGGElement>(null);
  const mouthRef = useRef<SVGPathElement>(null);
  const propRef = useRef<SVGGElement>(null);
  const gestureLive = useRef(gesture);
  gestureLive.current = gesture;

  useEffect(() => {
    let raf = 0;
    const t0 = performance.now();
    const loop = (now: number) => {
      const t = (now - t0) / 1000;
      const rig = gestureRig(gestureLive.current, t);
      lArmRef.current?.setAttribute("transform", `translate(58 118) rotate(${rig.lArm})`);
      lForeRef.current?.setAttribute("transform", `translate(0 46) rotate(${rig.lElbow})`);
      lHandRef.current?.setAttribute("transform", `translate(0 40) rotate(${rig.lWrist})`);
      rArmRef.current?.setAttribute("transform", `translate(142 118) rotate(${rig.rArm})`);
      rForeRef.current?.setAttribute("transform", `translate(0 46) rotate(${rig.rElbow})`);
      rHandRef.current?.setAttribute("transform", `translate(0 40) rotate(${rig.rWrist})`);
      setHand(lHandRef.current, rig.lHand);
      setHand(rHandRef.current, rig.rHand);
      headRef.current?.setAttribute(
        "transform",
        `rotate(${rig.headTilt} 100 54) translate(0 ${rig.headNod})`,
      );
      eyesOpenRef.current?.setAttribute(
        "opacity",
        rig.eyes === "happy" || rig.eyes === "sad" ? "0" : String(rig.eyeY > 0.35 ? 1 : 0),
      );
      eyesHappyRef.current?.setAttribute("opacity", rig.eyes === "happy" ? "1" : "0");
      eyesSadRef.current?.setAttribute("opacity", rig.eyes === "sad" ? "1" : "0");
      mouthRef.current?.setAttribute("d", mouthPath(rig.mouth));
      const q = rig.prop === "question" ? 1 : 0;
      propRef.current?.setAttribute("opacity", String(q));
      propRef.current?.setAttribute(
        "transform",
        `translate(148 ${10 + Math.sin(t * 3) * 3})`,
      );
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <svg
      viewBox="-24 -28 248 308"
      className="ced-holo-puppet h-[12rem] w-auto sm:h-[14rem] lg:h-[17rem]"
      overflow="visible"
      aria-hidden
    >
      <defs>
        <filter id="ced-holo-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient id="ced-holo-fill" cx="50%" cy="38%" r="68%">
          <stop offset="0%" stopColor="#d6ffff" stopOpacity="0.7" />
          <stop offset="50%" stopColor="#00e5ff" stopOpacity="0.32" />
          <stop offset="100%" stopColor="#003d55" stopOpacity="0.18" />
        </radialGradient>
        <pattern id="ced-holo-dots" width="4" height="4" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.75" fill="#9ffffa" opacity="0.9" />
        </pattern>
      </defs>

      <g filter="url(#ced-holo-glow)" fill="url(#ced-holo-fill)" stroke="#9ffffa" strokeWidth="1.7">
        <ellipse cx="100" cy="176" rx="18" ry="12" fill="url(#ced-holo-dots)" fillOpacity="0.35" />
        <ellipse cx="100" cy="176" rx="18" ry="12" fill="none" />

        <rect x="70" y="112" width="60" height="64" rx="18" fill="url(#ced-holo-dots)" fillOpacity="0.4" />
        <rect x="70" y="112" width="60" height="64" rx="18" />
        <rect x="78" y="128" width="44" height="18" rx="4" fill="#041820" stroke="#d6ffff" strokeWidth="1.3" />
        <text
          x="100"
          y="141"
          textAnchor="middle"
          fill="#f3ffff"
          fontFamily="Orbitron, ui-sans-serif, system-ui"
          fontSize="11"
          fontWeight="700"
          stroke="none"
        >
          CED
        </text>

        <g ref={headRef} transform="rotate(0 100 54)">
          <circle cx="100" cy="54" r="46" fill="url(#ced-holo-dots)" fillOpacity="0.45" />
          <circle cx="100" cy="54" r="46" />
          <ellipse cx="62" cy="48" rx="11" ry="15" />
          <ellipse cx="138" cy="48" rx="11" ry="15" />
          <circle cx="62" cy="33" r="2.6" fill="#d6ffff" stroke="none" />
          <circle cx="138" cy="33" r="2.6" fill="#d6ffff" stroke="none" />
          <rect x="72" y="42" width="56" height="44" rx="17" fill="#04141c" stroke="#9ffffa" strokeWidth="1.4" />
          <g ref={eyesOpenRef}>
            <circle cx="88" cy="62" r="7.5" fill="#7af7ff" stroke="none" />
            <circle cx="112" cy="62" r="7.5" fill="#7af7ff" stroke="none" />
            <circle cx="90" cy="60" r="2.2" fill="#04141c" stroke="none" />
            <circle cx="114" cy="60" r="2.2" fill="#04141c" stroke="none" />
          </g>
          <g ref={eyesHappyRef} opacity="0" fill="none" stroke="#7af7ff" strokeWidth="2.6" strokeLinecap="round">
            <path d="M80 64 Q88 56 96 64" />
            <path d="M104 64 Q112 56 120 64" />
          </g>
          <g ref={eyesSadRef} opacity="0" fill="none" stroke="#7af7ff" strokeWidth="2.6" strokeLinecap="round">
            <path d="M80 62 Q88 70 96 62" />
            <path d="M104 62 Q112 70 120 62" />
          </g>
          <path
            ref={mouthRef}
            d="M 88 78 Q 100 90 112 78"
            fill="none"
            stroke="#9ffffa"
            strokeWidth="2.4"
            strokeLinecap="round"
          />
        </g>

        <g ref={propRef} opacity="0">
          <circle cx="0" cy="0" r="15" fill="#04141c" fillOpacity="0.85" stroke="#9ffffa" strokeWidth="1.6" />
          <text
            x="0"
            y="6"
            textAnchor="middle"
            fill="#9ffffa"
            fontFamily="Orbitron, ui-sans-serif, system-ui"
            fontSize="18"
            fontWeight="700"
            stroke="none"
          >
            ?
          </text>
        </g>

        <g ref={lArmRef} transform="translate(58 118) rotate(12)">
          <line x1="0" y1="0" x2="0" y2="46" strokeWidth="11" strokeLinecap="round" />
          <g ref={lForeRef} transform="translate(0 46) rotate(8)">
            <line x1="0" y1="0" x2="0" y2="40" strokeWidth="9" strokeLinecap="round" />
            <g ref={lHandRef}>
              <HandShapes />
            </g>
          </g>
        </g>

        <g ref={rArmRef} transform="translate(142 118) rotate(12)">
          <line x1="0" y1="0" x2="0" y2="46" strokeWidth="11" strokeLinecap="round" />
          <g ref={rForeRef} transform="translate(0 46) rotate(8)">
            <line x1="0" y1="0" x2="0" y2="40" strokeWidth="9" strokeLinecap="round" />
            <g ref={rHandRef}>
              <HandShapes />
            </g>
          </g>
        </g>
      </g>
    </svg>
  );
}
