"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense } from "react";

import { CarouselRing } from "@/components/dashboard/carousel/CarouselRing";
import { CAROUSEL_CAMERA_Z } from "@/components/dashboard/carousel/carouselLayout";
import type { CarouselCardData } from "@/components/dashboard/carousel/types";

interface CarouselSceneProps {
  cards: CarouselCardData[];
  rotationSpeed: number;
  /** Si se omite, el stage llena el alto del contenedor padre (flex). */
  heightPx?: number;
  onPointerEnter: () => void;
  onPointerLeave: () => void;
}

function SceneInner({
  cards,
  rotationSpeed,
}: Pick<CarouselSceneProps, "cards" | "rotationSpeed">) {
  return (
    <>
      <ambientLight intensity={0.55} />
      <pointLight position={[4, 6, 4]} intensity={1.2} color="#00e5ff" />
      <pointLight position={[-4, -2, -3]} intensity={0.35} color="#7c3aed" />
      <CarouselRing cards={cards} rotationSpeed={rotationSpeed} />
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        enableRotate={false}
        autoRotate={false}
      />
    </>
  );
}

export function CarouselScene({
  cards,
  rotationSpeed,
  heightPx,
  onPointerEnter,
  onPointerLeave,
}: CarouselSceneProps) {
  const fixedHeight = heightPx != null;
  const stageStyle = fixedHeight
    ? { height: heightPx, maxHeight: heightPx }
    : { height: "100%", minHeight: 0 };

  return (
    <div
      className={`ced-carousel-stage relative w-full overflow-hidden${fixedHeight ? "" : " h-full"}`}
      style={stageStyle}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <Canvas
        className="ced-carousel-canvas !block h-full !max-h-full"
        style={
          fixedHeight
            ? { height: heightPx, width: "100%", display: "block" }
            : { height: "100%", width: "100%", display: "block" }
        }
        camera={{ position: [0, 0, CAROUSEL_CAMERA_Z], fov: 42 }}
        gl={{ alpha: true, antialias: true }}
        dpr={[1, 1.5]}
        frameloop="always"
      >
        <Suspense fallback={null}>
          <SceneInner cards={cards} rotationSpeed={rotationSpeed} />
        </Suspense>
      </Canvas>
    </div>
  );
}
