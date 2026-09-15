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
  useFrame((_, dt) => {
    ref.current.rotation.y += dt * 0.25;
    ref.current.rotation.x += dt * 0.08;
  });
  return (
    <mesh ref={ref} material={mat} renderOrder={0}>
      <icosahedronGeometry args={[1.2, 5]} />
    </mesh>
  );
}

function Rings() {
  const refs = useRef([]);
  const colors = ["#818cf8", "#a5b4fc", "#c7d2fe"];
  useFrame((_, dt) => {
    refs.current.forEach((r, i) => {
      if (!r) return;
      r.rotation.z += dt * (0.12 + i * 0.06);
      r.rotation.x += dt * (0.06 + i * 0.03);
    });
  });
  return (
    <>
      {colors.map((c, i) => (
        <mesh key={i} ref={(el) => (refs.current[i] = el)}>
          <torusGeometry args={[1.8 + i * 0.5, 0.014, 16, 100]} />
          <meshStandardMaterial
            color={c}
            emissive={c}
            emissiveIntensity={0.35}
            transparent
            opacity={0.55 - i * 0.1}
          />
        </mesh>
      ))}
    </>
  );
}

/* 6 glowing node spheres orbiting the core — ring + nodes share ONE tilted
   group so every node tracks the visible ring path exactly (Saturn-style).
   Labels are HTML overlay positioned from world coordinates. */
function Nodes({ onPositions }) {
  const labels = [
    "INCOME",
    "DEBT",
    "HISTORY",
    "FRAUD",
    "BEHAVIOR",
    "IDENTITY",
  ];
  const refs = useRef([]);
  const ORBIT_R = 2.6;

  useFrame(({ clock, camera, size }) => {
    const t = clock.getElapsedTime();
    const positions = [];
    const v = new THREE.Vector3();
    refs.current.forEach((r, i) => {
      if (!r) return;
      const angle = (i / labels.length) * Math.PI * 2 + t * 0.5;
      r.position.x = Math.cos(angle) * ORBIT_R;
      r.position.y = Math.sin(angle) * ORBIT_R;
      r.position.z = 0;
      // world position (nodes live inside the tilted group)
      r.getWorldPosition(v);
      v.project(camera);
      positions.push({
        x: ((v.x + 1) / 2) * size.width,
        y: ((-v.y + 1) / 2) * size.height,
        label: labels[i],
      });
    });
    if (onPositions) onPositions(positions);
  });

  return (
    <group rotation={[-0.42, 0, 0]}>
      {/* orbit path ring — same plane as the nodes */}
      <mesh>
        <torusGeometry args={[ORBIT_R, 0.01, 12, 140]} />
        <meshStandardMaterial
          color="#6366f1"
          emissive="#6366f1"
          emissiveIntensity={0.6}
          transparent
          opacity={0.5}
        />
      </mesh>
      {labels.map((_, i) => (
        <group key={i} ref={(el) => (refs.current[i] = el)}>
          <mesh>
            <sphereGeometry args={[0.18, 20, 20]} />
            <meshStandardMaterial
              color="#a5b4fc"
              emissive="#6366f1"
              emissiveIntensity={1}
            />
          </mesh>
          {/* small glow halo */}
          <mesh>
            <sphereGeometry args={[0.3, 16, 16]} />
            <meshStandardMaterial
              color="#818cf8"
              emissive="#6366f1"
              emissiveIntensity={0.8}
              transparent
              opacity={0.15}
            />
          </mesh>
        </group>
      ))}
    </group>
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

function SceneInner({ onPositions }) {
  return (
    <>
      <ambientLight intensity={0.35} />
      <pointLight position={[5, 5, 5]} intensity={0.9} color="#818cf8" />
      <pointLight position={[-5, -3, -5]} intensity={0.5} color="#6366f1" />
      <Core />
      <Rings />
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
