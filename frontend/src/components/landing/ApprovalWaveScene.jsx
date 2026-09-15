import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

const BAR_COUNT = 24;
const BAR_SPACING = 0.34;

function getWaveHeight(i, t) {
  const travel = Math.sin(i * 0.55 + t * 1.4);
  const secondary = Math.sin(i * 0.22 - t * 0.9) * 0.3;
  const base = ((Math.sin(i * 0.31) + 1) / 2) * 0.6 + 0.25;
  return Math.max(0.06, base * (travel * 0.7 + secondary + 0.85));
}

/* vertical bars that rise + fall like a heartbeat waveform across the stage */
function WaveBars() {
  const refs = useRef([]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    refs.current.forEach((r, i) => {
      if (!r) return;
      const h = getWaveHeight(i, t) * 1.9;
      r.scale.y = h;
      r.position.y = h / 2 - 0.1;
    });
  });
  const bars = Array.from({ length: BAR_COUNT }, (_, i) => {
    const x = (i - (BAR_COUNT - 1) / 2) * BAR_SPACING;
    return { key: i, x };
  });
  return (
    <>
      {bars.map((b) => (
        <group key={b.key} position={[b.x, 0, 0]}>
          <mesh ref={(el) => (refs.current[b.key] = el)}>
            <boxGeometry args={[0.16, 1, 0.16]} />
            <meshStandardMaterial
              color="#191a23"
              emissive="#191a23"
              emissiveIntensity={0.7}
              transparent
              opacity={0.85}
            />
          </mesh>
        </group>
      ))}
    </>
  );
}

/* glowing node that travels along the wave from left to right */
function RippleDot({ onPositions }) {
  const ref = useRef();
  useFrame(({ clock, camera, size }) => {
    const t = clock.getElapsedTime();
    const phase = (t * 0.6) % 1;
    const idx = phase * (BAR_COUNT - 1);
    const i0 = Math.floor(idx);
    const frac = idx - i0;
    const h0 = getWaveHeight(i0, t) * 1.9;
    const h1 = getWaveHeight(Math.min(i0 + 1, BAR_COUNT - 1), t) * 1.9;
    const x = (idx - (BAR_COUNT - 1) / 2) * BAR_SPACING;
    const y = (h0 + (h1 - h0) * frac) * 0.85;
    ref.current.position.set(x, y, 0.12);
    ref.current.scale.setScalar(1 + Math.sin(t * 6) * 0.25);

    if (onPositions) {
      const v = new THREE.Vector3(x, y, 0.12).project(camera);
      onPositions({
        x: ((v.x + 1) / 2) * size.width,
        y: ((-v.y + 1) / 2) * size.height,
      });
    }
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.14, 20, 20]} />
      <meshStandardMaterial
        color="#191a23"
        emissive="#191a23"
        emissiveIntensity={1.4}
      />
    </mesh>
  );
}

/* translucent flowing wave plane under the bars */
function WavePlane() {
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(9, 3.4, 48, 20);
    g.rotateZ(Math.PI / 2);
    return g;
  }, []);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      pos.setY(i, Math.sin(x * 1.4 + t * 1.2) * 0.22 + Math.sin(x * 0.6 - t * 0.7) * 0.12);
    }
    pos.needsUpdate = true;
    geo.computeVertexNormals();
  });
  return (
    <mesh geometry={geo} rotation={[-Math.PI / 2, Math.PI / 2, 0]} position={[0, -0.3, -0.6]}>
      <meshStandardMaterial
        color="#191a23"
        emissive="#191a23"
        emissiveIntensity={0.35}
        transparent
        opacity={0.28}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

/* upward-drifting glowing sparks */
function Sparks() {
  const count = 140;
  const data = useMemo(() => {
    const positions = new Float32Array(count * 3);
    const speeds = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 10;
      positions[i * 3 + 1] = Math.random() * 4 - 1;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 6 - 1;
      speeds[i] = 0.1 + Math.random() * 0.25;
    }
    return { positions, speeds };
  }, []);
  const ref = useRef();
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const arr = ref.current.geometry.attributes.position.array;
    for (let i = 0; i < count; i++) {
      arr[i * 3 + 1] += data.speeds[i] * 0.008;
      if (arr[i * 3 + 1] > 2.2) arr[i * 3 + 1] = -1.2;
      arr[i * 3] += Math.sin(t * 0.8 + i) * 0.0006;
    }
    ref.current.geometry.attributes.position.needsUpdate = true;
    ref.current.rotation.y = t * 0.05;
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" count={count} array={data.positions} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.03} color="#191a23" transparent opacity={0.5} sizeAttenuation />
    </points>
  );
}

function SceneInner({ onDot }) {
  return (
    <>
      <ambientLight intensity={0.35} />
      <pointLight position={[0, 4, 6]} intensity={1} color="#a5b4fc" />
      <pointLight position={[-6, -2, -4]} intensity={0.5} color="#6366f1" />
      <WaveBars />
      <WavePlane />
      <RippleDot onPositions={onDot} />
      <Sparks />
    </>
  );
}

/* Distinct 3D scene for the bottom CTA: a pulsing approval waveform */
export default function ApprovalWaveScene({ className, onDot }) {
  return (
    <div className={className} style={{ width: "100%", height: "100%" }}>
      <Canvas
        camera={{ position: [0, 1.6, 6.4], fov: 48 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: "transparent" }}
      >
        <SceneInner onDot={onDot} />
      </Canvas>
    </div>
  );
}