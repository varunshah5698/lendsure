import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

function Core() {
  const ref = useRef();
  const mat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#6366f1",
        emissive: "#4f46e5",
        emissiveIntensity: 0.5,
        metalness: 0.8,
        roughness: 0.2,
        transparent: true,
        opacity: 0.95,
        depthWrite: true,
      }),
    []
  );
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ref.current.rotation.y += 0.0042;
    ref.current.rotation.x += 0.0013;
    // slow breathing core
    const s = 1 + Math.sin(t * 0.9) * 0.035;
    ref.current.scale.set(s, s, s);
    mat.emissiveIntensity = 0.5 + Math.sin(t * 0.9) * 0.12;
  });
  return (
    <mesh ref={ref} material={mat} renderOrder={0}>
      <icosahedronGeometry args={[1.05, 5]} />
    </mesh>
  );
}

function CoreShell() {
  const ref = useRef();
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ref.current.rotation.y -= 0.0016;
    const s = 1.02 + Math.sin(t * 0.9 + 1) * 0.02;
    ref.current.scale.set(s, s, s);
  });
  return (
    <mesh ref={ref} renderOrder={1}>
      <icosahedronGeometry args={[1.28, 1]} />
      <meshBasicMaterial color="#a5b4fc" wireframe transparent opacity={0.22} />
    </mesh>
  );
}

/* Six glowing nodes, each revolving on its OWN tilted orbital disc —
   wide radius separation, gentle inclinations, even phasing: structured
   orbits, never spaghetti. Inner discs run faster (Kepler-style).
   Labels are pushed radially outward from the projected center so they
   cannot stack on each other. */
const ORBITS = [
  { label: "INCOME", r: 2.2, tilt: [-0.34, 0, 0.16], speed: 0.5, phase: 0.0 },
  { label: "DEBT", r: 2.38, tilt: [-0.18, 0, -0.22], speed: 0.45, phase: 1.05 },
  { label: "HISTORY", r: 2.56, tilt: [0.2, 0, 0.2], speed: 0.4, phase: 2.1 },
  { label: "FRAUD", r: 2.74, tilt: [-0.1, 0, -0.1], speed: 0.36, phase: 3.15 },
  { label: "BEHAVIOR", r: 2.92, tilt: [0.32, 0, -0.2], speed: 0.32, phase: 4.2 },
  { label: "IDENTITY", r: 3.1, tilt: [-0.26, 0, 0.1], speed: 0.29, phase: 5.25 },
];

function Nodes({ onPositions }) {
  const refs = useRef([]);

  useFrame(({ clock, camera, size }) => {
    const t = clock.getElapsedTime();
    const positions = [];
    const v = new THREE.Vector3();
    // projected center: labels are pushed away from it radially
    const c = new THREE.Vector3(0, 0, 0).project(camera);
    const cx = ((c.x + 1) / 2) * size.width;
    const cy = ((-c.y + 1) / 2) * size.height;
    refs.current.forEach((r, i) => {
      if (!r) return;
      const o = ORBITS[i];
      const angle = o.phase + t * o.speed;
      r.position.x = Math.cos(angle) * o.r;
      r.position.y = Math.sin(angle) * o.r;
      r.position.z = 0;
      // breathing pulse so each node feels alive
      const s = 1 + Math.sin(t * 2.4 + i * 1.3) * 0.12;
      r.scale.set(s, s, s);
      // world position (nodes live inside their own tilted disc group)
      r.getWorldPosition(v);
      v.project(camera);
      const nx = ((v.x + 1) / 2) * size.width;
      const ny = ((-v.y + 1) / 2) * size.height;
      let dx = nx - cx, dy = ny - cy;
      const len = Math.hypot(dx, dy) || 1;
      positions.push({
        x: nx + (dx / len) * 34,
        y: ny + (dy / len) * 34,
        label: o.label,
      });
    });
    if (onPositions) onPositions(positions);
  });

  return (
    <>
      {ORBITS.map((o, i) => (
        <group key={o.label} rotation={o.tilt}>
          {/* this dimension's own orbital disc */}
          <mesh>
            <torusGeometry args={[o.r, 0.008, 12, 160]} />
            <meshStandardMaterial
              color="#6366f1"
              emissive="#6366f1"
              emissiveIntensity={0.55}
              transparent
              opacity={0.32}
            />
          </mesh>
          <group ref={(el) => (refs.current[i] = el)}>
            <mesh>
              <sphereGeometry args={[0.16, 20, 20]} />
              <meshStandardMaterial
                color="#a5b4fc"
                emissive="#6366f1"
                emissiveIntensity={1}
              />
            </mesh>
            {/* small glow halo */}
            <mesh>
              <sphereGeometry args={[0.27, 16, 16]} />
              <meshStandardMaterial
                color="#818cf8"
                emissive="#6366f1"
                emissiveIntensity={0.8}
                transparent
                opacity={0.15}
              />
            </mesh>
          </group>
        </group>
      ))}
    </>
  );
}

function DataLines() {
  const refs = useRef([]);
  const count = 8;
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    refs.current.forEach((r, i) => {
      if (!r) return;
      const angle = (i / count) * Math.PI * 2;
      r.position.x = Math.cos(angle) * 1.65;
      r.position.z = Math.sin(angle) * 1.65;
      r.lookAt(0, 0, 0);
      const s = 0.5 + Math.sin(t * 2 + i) * 0.3;
      r.scale.set(1, 1, s);
    });
  });
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <mesh key={i} ref={(el) => (refs.current[i] = el)}>
          <cylinderGeometry args={[0.006, 0.006, 0.8, 8]} />
          <meshStandardMaterial
            color="#4f46e5"
            emissive="#4f46e5"
            emissiveIntensity={0.4}
            transparent
            opacity={0.35}
          />
        </mesh>
      ))}
    </>
  );
}

function Particles() {
  const count = 220;
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 14;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 9;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 14;
    }
    return arr;
  }, []);
  const ref = useRef();
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ref.current.rotation.y = t * 0.025;
    ref.current.rotation.x = Math.sin(t * 0.1) * 0.12;
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.025}
        color="#6366f1"
        transparent
        opacity={0.45}
        sizeAttenuation
      />
    </points>
  );
}

function CameraRig() {
  useFrame(({ clock, camera }) => {
    const t = clock.getElapsedTime();
    // gentle cinematic drift around the core
    camera.position.x = Math.sin(t * 0.12) * 0.55;
    camera.position.y = Math.cos(t * 0.09) * 0.35;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

function SceneInner({ onPositions }) {
  return (
    <>
      <ambientLight intensity={0.35} />
      <pointLight position={[5, 5, 5]} intensity={0.9} color="#818cf8" />
      <pointLight position={[-5, -3, -5]} intensity={0.5} color="#6366f1" />
      <CameraRig />
      <Core />
      <CoreShell />
      <Nodes onPositions={onPositions} />
      <DataLines />
      <Particles />
    </>
  );
}

export default function RiskCoreScene({ className, onLabels }) {
  return (
    <div className={className} style={{ width: "100%", height: "100%" }}>
      <Canvas
        camera={{ position: [0, 0, 7.4], fov: 50 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: "transparent" }}
      >
        <SceneInner onPositions={onLabels} />
      </Canvas>
    </div>
  );
}
