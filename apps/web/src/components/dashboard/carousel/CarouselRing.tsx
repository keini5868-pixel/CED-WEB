"use client";

import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

import { HudCarouselCard } from "@/components/dashboard/carousel/HudCarouselCard";
import type { CarouselCardData } from "@/components/dashboard/carousel/types";
import {
  CAROUSEL_HTML_DISTANCE,
  CAROUSEL_RADIUS,
  CAROUSEL_RING_Y,
  CARD_HEIGHT_PX,
  CARD_WIDTH_PX,
} from "@/components/dashboard/carousel/carouselLayout";

interface CarouselRingProps {
  cards: CarouselCardData[];
  rotationSpeed: number;
}

function CardSlot({
  card,
  index,
  total,
}: {
  card: CarouselCardData;
  index: number;
  total: number;
}) {
  const angle = (index / total) * Math.PI * 2;
  const x = Math.sin(angle) * CAROUSEL_RADIUS;
  const z = Math.cos(angle) * CAROUSEL_RADIUS;

  return (
    <group position={[x, 0, z]} rotation={[0, angle, 0]}>
      <Html
        transform
        center
        distanceFactor={CAROUSEL_HTML_DISTANCE}
        zIndexRange={[10, 0]}
        wrapperClass="ced-carousel-html-wrap"
        style={{
          width: CARD_WIDTH_PX,
          height: CARD_HEIGHT_PX,
          overflow: "hidden",
          pointerEvents: "none",
        }}
      >
        <HudCarouselCard card={card} />
      </Html>
    </group>
  );
}

export function CarouselRing({ cards, rotationSpeed }: CarouselRingProps) {
  const groupRef = useRef<THREE.Group>(null);
  const total = cards.length;

  useFrame(() => {
    if (!groupRef.current || rotationSpeed === 0) return;
    groupRef.current.rotation.y += rotationSpeed;
  });

  return (
    <group ref={groupRef} position={[0, CAROUSEL_RING_Y, 0]}>
      {cards.map((card, index) => (
        <CardSlot key={card.id} card={card} index={index} total={total} />
      ))}
    </group>
  );
}
