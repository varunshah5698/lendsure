import { useRef, useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";

/**
 * 3D Atom Structure Hero Scene
 * Rutherford-Bohr Atomic Model for LendSure:
 * - Clustered Protons (Red) & Neutrons (Blue) with glossy finish
 * - Golden energy boundary ring encircling the nucleus
 * - 4 crossing 3D elliptical orbits
 * - 4 rotating electrons: MONEY, FRAUD, CREDIT, TRUST
 */

// Balanced front-visible coordinates for nucleus particles (protons & neutrons)
const NUCLEUS_PARTICLES = [
  // Front-facing layer (highly visible)
  { pos: [0.12, 0.14, 0.28], type: "neutron", r: 0.24 },
  { pos: [-0.14, -0.12, 0.26], type: "proton", r: 0.25 },
  { pos: [0.22, -0.15, 0.22], type: "neutron", r: 0.23 },
  { pos: [-0.22, 0.16, 0.22], type: "proton", r: 0.24 },
  { pos: [-0.02, 0.26, 0.2], type: "proton", r: 0.23 },
  { pos: [0.02, -0.26, 0.2], type: "neutron", r: 0.23 },

  // Center layer
  { pos: [0, 0, 0.05], type: "proton", r: 0.27 },
  { pos: [0.32, 0.08, 0], type: "neutron", r: 0.24 },
  { pos: [-0.31, -0.06, 0], type: "proton", r: 0.24 },
  { pos: [0.12, 0.33, 0], type: "neutron", r: 0.23 },
  { pos: [-0.11, -0.32, 0], type: "proton", r: 0.23 },

  // Rear layer
  { pos: [0.18, 0.12, -0.24], type: "proton", r: 0.24 },
  { pos: [-0.16, -0.14, -0.24], type: "neutron", r: 0.24 },
  { pos: [-0.2, 0.18, -0.2], type: "neutron", r: 0.23 },
  { pos: [0.2, -0.18, -0.2], type: "proton", r: 0.23 },
  { pos: [0, 0, -0.3], type: "neutron", r: 0.24 },
];

function Nucleus() {
  const groupRef = useRef();
  const ringRef = useRef();

  // Glossy candy-lacquer materials for Protons (Red) and Neutrons (Blue)
  const protonMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#dc2626",
        emissive: "#991b1b",
        emissiveIntensity: 0.45,
        roughness: 0.15,
        metalness: 0.2,
      }),
    []
  );

  const neutronMat = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#1d4ed8",
        emissive: "#1e3a8a",
        emissiveIntensity: 0.45,
        roughness: 0.15,
        metalness: 0.2,
      }),
    []
  );

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.24;
      groupRef.current.rotation.x = Math.sin(t * 0.18) * 0.16;
      // Subtle organic breathing scale
      const s = 1 + Math.sin(t * 1.5) * 0.035;
      groupRef.current.scale.set(s, s, s);
    }
    if (ringRef.current) {
      ringRef.current.rotation.z = -t * 0.32;
      ringRef.current.rotation.y = Math.cos(t * 0.22) * 0.22;
    }
  });

  return (
    <group>
      {/* Central clustered nucleus particles */}
      <group ref={groupRef}>
        {NUCLEUS_PARTICLES.map((p, i) => (
          <mesh
            key={i}
            position={p.pos}
            material={p.type === "proton" ? protonMat : neutronMat}
          >
            <sphereGeometry args={[p.r, 24, 24]} />
          </mesh>
        ))}

        {/* Soft amber translucent nucleus glow sphere */}
        <mesh>
          <sphereGeometry args={[0.78, 20, 20]} />
          <meshStandardMaterial
            color="#fbbf24"
            emissive="#f59e0b"
            emissiveIntensity={0.25}
            transparent
            opacity={0.12}
            depthWrite={false}
          />
        </mesh>

      </group>

      {/* "Borrowers" label — outside the rotating nucleus group so it stays
          upright, static and readable at all times (a 3D-tracked DOM pill) */}
      <Html center distanceFactor={8} position={[0, 0.02, 0]} style={{ pointerEvents: "none" }} zIndexRange={[20, 0]}>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "7px",
            padding: "6px 14px",
            borderRadius: "999px",
            background: "rgba(251,191,36,0.12)",
            border: "1.5px solid rgba(251,191,36,0.55)",
            boxShadow: "0 0 26px rgba(245,158,11,0.35), inset 0 0 12px rgba(251,191,36,0.08)",
            color: "#fde68a",
            fontFamily: "'Inter', system-ui, sans-serif",
            fontWeight: 700,
            fontSize: "12px",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            textShadow: "0 0 10px rgba(251,191,36,0.55)",
            whiteSpace: "nowrap",
            userSelect: "none",
            backdropFilter: "blur(6px)",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#fbbf24",
              boxShadow: "0 0 8px #fbbf24",
              display: "inline-block",
            }}
          />
          Borrowers
        </span>
      </Html>

      {/* Golden/Amber boundary ring around nucleus (like yellow circle in drawing) */}
      <group ref={ringRef}>
        <mesh rotation={[0.42, 0.22, 0]}>
          <torusGeometry args={[0.92, 0.016, 16, 80]} />
          <meshStandardMaterial
            color="#f59e0b"
            emissive="#d97706"
            emissiveIntensity={0.8}
            metalness={0.7}
            roughness={0.2}
          />
        </mesh>
        <mesh rotation={[-0.32, -0.38, 0]}>
          <torusGeometry args={[0.96, 0.01, 14, 80]} />
          <meshBasicMaterial
            color="#fbbf24"
            transparent
            opacity={0.35}
          />
        </mesh>
      </group>
    </group>
  );
}

/**
 * 4 Crossing Elliptical Orbits with 4 Orbiting Electrons:
 * 1. MONEY (Emerald / Green)
 * 2. FRAUD (Crimson / Coral Red)
 * 3. CREDIT (Indigo / Violet)
 * 4. TRUST (Cyan / Sky Blue)
 */
const ORBIT_CONFIGS = [
  {
    id: "money",
    label: "MONEY",
    icon: "₹",
    sub: "Capital Flow",
    color: "#10b981",
    emissive: "#059669",
    orbitColor: "#94a3b8",
    a: 2.62, // semi-major axis
    b: 1.42, // semi-minor axis
    speed: 0.65,
    phase: 0.2,
    rotation: [-0.48, 0.35, -0.65],
  },
  {
    id: "fraud",
    label: "FRAUD",
    icon: "🛡️",
    sub: "Risk Radar",
    color: "#ef4444",
    emissive: "#dc2626",
    orbitColor: "#94a3b8",
    a: 2.65,
    b: 1.45,
    speed: -0.6,
    phase: 2.1,
    rotation: [0.52, -0.3, 0.65],
  },
  {
    id: "credit",
    label: "CREDIT",
    icon: "📊",
    sub: "Score & Debt",
    color: "#6366f1",
    emissive: "#4f46e5",
    orbitColor: "#94a3b8",
    a: 2.68,
    b: 1.42,
    speed: 0.58,
    phase: 4.0,
    rotation: [0.25, 0.65, -0.28],
  },
  {
    id: "trust",
    label: "TRUST",
    icon: "⚡",
    sub: "Repayment",
    color: "#06b6d4",
    emissive: "#0891b2",
    orbitColor: "#94a3b8",
    a: 2.64,
    b: 1.46,
    speed: -0.68,
    phase: 1.2,
    rotation: [-0.3, -0.6, 0.35],
  },
];

function AtomOrbitsAndElectrons({ onPositions }) {
  const electronRefs = useRef([]);
  const trailRefs = useRef([[], [], [], []]);

  // Pre-generate smooth ellipse geometry points for orbit rings
  const orbitGeometries = useMemo(() => {
    return ORBIT_CONFIGS.map((cfg) => {
      const curve = new THREE.EllipseCurve(
        0, 0,
        cfg.a, cfg.b,
        0, 2 * Math.PI,
        false, 0
      );
      const points = curve.getPoints(128);
      const points3D = points.map((p) => new THREE.Vector3(p.x, p.y, 0));
      const catmull = new THREE.CatmullRomCurve3(points3D, true);
      return new THREE.TubeGeometry(catmull, 128, 0.013, 8, true);
    });
  }, []);

  useFrame(({ clock, camera, size }) => {
    const t = clock.getElapsedTime();
    const positions = [];
    const v = new THREE.Vector3();

    // Center screen projection for radial label positioning
    const c = new THREE.Vector3(0, 0, 0).project(camera);
    const cx = ((c.x + 1) / 2) * size.width;
    const cy = ((-c.y + 1) / 2) * size.height;

    ORBIT_CONFIGS.forEach((cfg, i) => {
      const elRef = electronRefs.current[i];
      if (!elRef) return;

      const angle = cfg.phase + t * cfg.speed;
      const x = Math.cos(angle) * cfg.a;
      const y = Math.sin(angle) * cfg.b;
      elRef.position.set(x, y, 0);

      // Pulse electron scale
      const pulse = 1 + Math.sin(t * 3.5 + i * 1.5) * 0.14;
      elRef.scale.set(pulse, pulse, pulse);

      // Update trailing sparks behind each electron
      const trails = trailRefs.current[i];
      if (trails) {
        trails.forEach((trailEl, trIdx) => {
          if (!trailEl) return;
          const trailAngle = angle - (trIdx + 1) * 0.07 * Math.sign(cfg.speed);
          trailEl.position.set(
            Math.cos(trailAngle) * cfg.a,
            Math.sin(trailAngle) * cfg.b,
            0
          );
        });
      }

      // Compute projected 2D coordinates for DOM labels
      elRef.getWorldPosition(v);
      v.project(camera);
      const nx = ((v.x + 1) / 2) * size.width;
      const ny = ((-v.y + 1) / 2) * size.height;

      let dx = nx - cx;
      let dy = ny - cy;
      const len = Math.hypot(dx, dy) || 1;

      // Keep badges comfortably within bounds above the bottom HUD
      const lx = Math.min(Math.max(nx + (dx / len) * 30, 44), size.width - 44);
      const ly = Math.min(Math.max(ny + (dy / len) * 30, 26), size.height - 68);

      positions.push({
        id: cfg.id,
        label: cfg.label,
        icon: cfg.icon,
        sub: cfg.sub,
        color: cfg.color,
        x: lx,
        y: ly,
      });
    });

    if (onPositions) onPositions(positions);
  });

  return (
    <>
      {ORBIT_CONFIGS.map((cfg, i) => (
        <group key={cfg.id} rotation={cfg.rotation}>
          {/* Smooth elliptical 3D orbit line (subtle metallic ring with color sheen) */}
          <mesh geometry={orbitGeometries[i]}>
            <meshStandardMaterial
              color="#cbd5e1"
              emissive={cfg.color}
              emissiveIntensity={0.35}
              roughness={0.25}
              metalness={0.65}
              transparent
              opacity={0.42}
            />
          </mesh>

          {/* Trailing sparks behind the electron */}
          {[0, 1, 2].map((trIdx) => (
            <mesh
              key={trIdx}
              ref={(el) => {
                if (!trailRefs.current[i]) trailRefs.current[i] = [];
                trailRefs.current[i][trIdx] = el;
              }}
              scale={0.075 - trIdx * 0.02}
            >
              <sphereGeometry args={[1, 10, 10]} />
              <meshBasicMaterial
                color={cfg.color}
                transparent
                opacity={0.42 - trIdx * 0.12}
              />
            </mesh>
          ))}

          {/* Orbiting Electron Group */}
          <group ref={(el) => (electronRefs.current[i] = el)}>
            {/* Core Electron Sphere (emerald/red/indigo/cyan) */}
            <mesh>
              <sphereGeometry args={[0.17, 24, 24]} />
              <meshStandardMaterial
                color={cfg.color}
                emissive={cfg.emissive}
                emissiveIntensity={1.3}
                roughness={0.12}
                metalness={0.85}
              />
            </mesh>

            {/* Glowing outer halo */}
            <mesh>
              <sphereGeometry args={[0.28, 16, 16]} />
              <meshStandardMaterial
                color={cfg.color}
                emissive={cfg.color}
                emissiveIntensity={0.9}
                transparent
                opacity={0.24}
                depthWrite={false}
              />
            </mesh>

            {/* Outer soft aura */}
            <mesh>
              <sphereGeometry args={[0.4, 14, 14]} />
              <meshBasicMaterial
                color={cfg.color}
                transparent
                opacity={0.07}
                depthWrite={false}
              />
            </mesh>
          </group>
        </group>
      ))}
    </>
  );
}

function AmbientDust() {
  const count = 160;
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 12;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 8;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 10;
    }
    return arr;
  }, []);

  const ref = useRef();
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (ref.current) {
      ref.current.rotation.y = t * 0.02;
      ref.current.rotation.x = Math.sin(t * 0.08) * 0.08;
    }
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
        size={0.022}
        color="#818cf8"
        transparent
        opacity={0.3}
        sizeAttenuation
      />
    </points>
  );
}

function CameraRig() {
  useFrame(({ clock, camera }) => {
    const t = clock.getElapsedTime();
    // Gentle 3D perspective floating
    camera.position.x = Math.sin(t * 0.14) * 0.3;
    camera.position.y = -0.15 + Math.cos(t * 0.11) * 0.18;
    camera.lookAt(0, -0.05, 0);
  });
  return null;
}

function AtomSceneInner({ onPositions }) {
  return (
    <>
      <ambientLight intensity={0.65} />
      {/* Golden core light from nucleus */}
      <pointLight position={[0, 0, 0]} intensity={1.6} color="#fbbf24" distance={5} />
      {/* Front bright key light for crisp reflections */}
      <directionalLight position={[0, 4, 6]} intensity={0.9} color="#ffffff" />
      {/* Multi-directional rim lights */}
      <pointLight position={[6, 5, 5]} intensity={0.9} color="#38bdf8" />
      <pointLight position={[-6, -4, -4]} intensity={0.7} color="#ec4899" />
      <pointLight position={[0, 7, 3]} intensity={0.5} color="#a7f3d0" />

      <CameraRig />
      <Nucleus />
      <AtomOrbitsAndElectrons onPositions={onPositions} />
      <AmbientDust />
    </>
  );
}

export default function RiskCoreScene({ className, onLabels }) {
  return (
    <div className={className} style={{ width: "100%", height: "100%" }}>
      <Canvas
        camera={{ position: [0, -0.1, 8.4], fov: 46 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, alpha: true }}
        style={{ background: "transparent" }}
      >
        <AtomSceneInner onPositions={onLabels} />
      </Canvas>
    </div>
  );
}
