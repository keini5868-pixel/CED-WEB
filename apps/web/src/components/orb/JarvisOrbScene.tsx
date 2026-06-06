"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

import type { OrbState, VoicePaletteId } from "@ced/types";

import { paletteColors, stateSpeed } from "@/components/orb/orbPalette";

interface SceneProps {
  orbState: OrbState;
  audioLevel: number;
  palette: VoicePaletteId;
}

function JarvisOrbMesh({ orbState, audioLevel, palette }: SceneProps) {
  const group = useRef<THREE.Group>(null);
  const core = useRef<THREE.Mesh>(null);
  const ring1 = useRef<THREE.Mesh>(null);
  const ring2 = useRef<THREE.Mesh>(null);
  const ring3 = useRef<THREE.Mesh>(null);
  const particles = useRef<THREE.Points>(null);
  const sparks = useRef<THREE.Points>(null);
  const tick = useRef(0);
  const sparkFlash = useRef(0);

  const colors = paletteColors(palette);
  const isError = orbState === "error";
  const primary = new THREE.Color(isError ? colors.error : colors.primary);
  const secondary = new THREE.Color(
    orbState === "processing" ? colors.secondary : colors.primary,
  );

  const sparkGeometry = useMemo(() => {
    const count = 48;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      const r = 0.55 + Math.random() * 0.55;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geometry;
  }, []);

  const particleGeometry = useMemo(() => {
    const count = 120;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      const r = 0.9 + Math.random() * 0.5;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = r * Math.cos(phi);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geometry;
  }, []);

  useFrame((_, delta) => {
    tick.current += delta;
    const speed = stateSpeed(orbState);
    const pulse =
      orbState === "idle"
        ? 0.55 + Math.sin(tick.current * 1.2) * 0.12
        : 0.75 + audioLevel * 0.55;

    if (group.current) group.current.rotation.y += delta * speed * 0.35;

    if (ring1.current) {
      ring1.current.rotation.x += delta * speed * 0.8;
      ring1.current.rotation.z += delta * speed * 0.3;
      ring1.current.scale.setScalar(1 + audioLevel * 0.08);
    }
    if (ring2.current) {
      ring2.current.rotation.y -= delta * speed * 1.1;
      ring2.current.scale.setScalar(1 + audioLevel * 0.12);
    }
    if (ring3.current) {
      ring3.current.rotation.x -= delta * speed * 0.6;
      ring3.current.rotation.y += delta * speed * 0.5;
    }

    if (core.current) {
      const mat = core.current.material as THREE.MeshStandardMaterial;
      const mix =
        orbState === "processing"
          ? (Math.sin(tick.current * 4) + 1) / 2
          : audioLevel;
      mat.emissive.lerpColors(primary, secondary, mix * 0.6);
      mat.emissiveIntensity = pulse * 1.8;
      core.current.scale.setScalar(0.9 + audioLevel * 0.15);
    }

    if (particles.current) {
      particles.current.rotation.y += delta * speed * 0.2;
      const mat = particles.current.material as THREE.PointsMaterial;
      mat.opacity =
        orbState === "processing"
          ? 0.35 + Math.sin(tick.current * 6) * 0.15
          : 0.12 + audioLevel * 0.35;
    }

    if (sparks.current) {
      sparks.current.rotation.y -= delta * speed * 0.45;
      sparks.current.rotation.x += delta * speed * 0.2;
      const mat = sparks.current.material as THREE.PointsMaterial;
      sparkFlash.current += delta;
      const burst =
        orbState === "processing"
          ? 0.55 + Math.sin(tick.current * 9) * 0.35
          : 0.15 + audioLevel * 0.65;
      mat.opacity = burst + (sparkFlash.current % 0.35 < 0.05 ? 0.5 : 0);
      mat.size = 0.02 + burst * 0.06;
    }
  });

  return (
    <group ref={group}>
      <mesh ref={core}>
        <sphereGeometry args={[0.42, 48, 48]} />
        <meshStandardMaterial
          color="#021018"
          emissive={primary}
          emissiveIntensity={0.95}
          metalness={0.55}
          roughness={0.28}
        />
      </mesh>

      <mesh ref={ring1} rotation={[Math.PI / 2.2, 0, 0]}>
        <torusGeometry args={[0.72, 0.018, 16, 96]} />
        <meshBasicMaterial color={primary} transparent opacity={0.85} />
      </mesh>
      <mesh ref={ring2} rotation={[0.4, Math.PI / 3, 0]}>
        <torusGeometry args={[0.88, 0.012, 12, 96]} />
        <meshBasicMaterial color={primary} transparent opacity={0.55} />
      </mesh>
      <mesh ref={ring3} rotation={[Math.PI / 5, 0.2, Math.PI / 4]}>
        <torusGeometry args={[1.02, 0.008, 8, 64]} />
        <meshBasicMaterial color={secondary} transparent opacity={0.45} />
      </mesh>

      <points ref={particles} geometry={particleGeometry} frustumCulled={false}>
        <pointsMaterial
          color={primary}
          size={0.025}
          transparent
          opacity={0.2}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>

      <points ref={sparks} geometry={sparkGeometry} frustumCulled={false}>
        <pointsMaterial
          color={secondary}
          size={0.035}
          transparent
          opacity={0.4}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          sizeAttenuation
        />
      </points>

      {(orbState === "listening" || orbState === "speaking") && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[1.05 + audioLevel * 0.2, 1.15 + audioLevel * 0.35, 64]} />
          <meshBasicMaterial
            color={primary}
            transparent
            opacity={0.25 + audioLevel * 0.4}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}
    </group>
  );
}

export default function JarvisOrbScene(props: SceneProps) {
  return (
    <div className="h-[min(52vw,280px)] w-[min(52vw,280px)] max-h-[320px] max-w-[320px] md:h-[300px] md:w-[300px]">
      <Canvas
        camera={{ position: [0, 0, 3.2], fov: 42 }}
        dpr={[1, 2]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: "transparent" }}
      >
        <ambientLight intensity={0.18} />
        <pointLight position={[2, 2, 2]} intensity={0.85} color="#00e5ff" />
        <pointLight position={[-2, -1, 1]} intensity={0.45} color="#7c4dff" />
        <Suspense fallback={null}>
          <JarvisOrbMesh {...props} />
        </Suspense>
      </Canvas>
    </div>
  );
}
