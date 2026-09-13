"use client"

import * as React from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { MeshTransmissionMaterial, Environment, Lightformer } from "@react-three/drei";
import { motion, useAnimationControls, useReducedMotion } from "motion/react";

function resolveFontStack(stack: string): string {
  if (typeof window === "undefined") return stack;
  const root = getComputedStyle(document.documentElement);
  return stack.replace(/var\(\s*(--[\w-]+)\s*\)/g, (_m, name: string) => {
    const v = root.getPropertyValue(name).trim();
    return v || "serif";
  });
}

function drawHeadline(
  text: string,
  color: string,
  fontFamily: string,
  italic: boolean,
): THREE.CanvasTexture | null {
  if (typeof document === "undefined") return null;

  const W = 2048;
  const H = 640;
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.clearRect(0, 0, W, H);

  const stack = resolveFontStack(fontFamily);
  const style = italic ? "italic " : "";
  let size = 460;
  do {
    ctx.font = `${style}500 ${size}px ${stack}`;
    size -= 8;
  } while (ctx.measureText(text).width > W * 0.92 && size > 40);

  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, W / 2, H / 2);

  const t = new THREE.CanvasTexture(canvas);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.needsUpdate = true;
  return t;
}

function useHeadlineTexture(
  text: string,
  color: string,
  fontFamily: string,
  italic: boolean,
) {
  const [texture, setTexture] = React.useState(() =>
    drawHeadline(text, color, fontFamily, italic),
  );

  React.useEffect(() => {
    let cancelled = false;
    const rebake = () => {
      if (!cancelled) setTexture(drawHeadline(text, color, fontFamily, italic));
    };
    if (document.fonts?.ready) {
      document.fonts.ready.then(rebake).catch(rebake);
    } else {
      rebake();
    }
    return () => {
      cancelled = true;
    };
  }, [text, color, fontFamily, italic]);

  React.useEffect(() => () => texture?.dispose(), [texture]);

  return texture;
}

function Headline({ texture, z = -2.2 }: { texture: THREE.CanvasTexture | null; z?: number }) {
  const { viewport } = useThree();
  const width = Math.min(viewport.width * 0.96, 16);
  const height = width * (640 / 2048);

  if (!texture) return null;

  return (
    <mesh position={[0, 0, z]} renderOrder={-1}>
      <planeGeometry args={[width, height]} />
      <meshBasicMaterial map={texture} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

function Crystal({
  progress,
  reducedMotion,
  dispersion,
  tint,
  spec,
}: {
  progress: React.RefObject<number>;
  reducedMotion: boolean;
  dispersion: number;
  tint: string;
  spec: QualitySpec;
}) {
  const ref = React.useRef<THREE.Mesh>(null);
  const pointer = React.useRef({ x: 0, y: 0 });
  const { viewport } = useThree();

  const portrait = viewport.width < viewport.height;
  const fit = Math.min(viewport.width, viewport.height);
  const baseScale = THREE.MathUtils.clamp(fit / 5.1, portrait ? 0.3 : 0.42, 1);

  React.useEffect(() => {
    if (reducedMotion) return;
    const onMove = (e: PointerEvent) => {
      pointer.current.x = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.current.y = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [reducedMotion]);

  useFrame((state, delta) => {
    const mesh = ref.current;
    if (!mesh) return;
    const p = progress.current ?? 0;
    const t = state.clock.elapsedTime;

    const spin = reducedMotion ? 0 : t * 0.13 + p * Math.PI * 1.1;
    mesh.rotation.y = spin;
    mesh.rotation.x = Math.sin(t * 0.21) * 0.14 + p * 0.4;
    mesh.rotation.z = Math.cos(t * 0.17) * 0.08;

    const tx = pointer.current.x * 0.35;
    const ty = -pointer.current.y * 0.28;
    mesh.position.x += (tx - mesh.position.x) * Math.min(1, delta * 2.2);
    mesh.position.y += (ty - mesh.position.y) * Math.min(1, delta * 2.2);

    mesh.scale.setScalar(baseScale * (1 + p * 0.18));
  });

  return (
    <mesh ref={ref} position={[0, 0, 0]}>
      <icosahedronGeometry args={[1.32, 0]} />
      <MeshTransmissionMaterial
        transmission={1}
        thickness={1.35}
        roughness={0.03}
        ior={1.92}
        chromaticAberration={dispersion}
        anisotropy={0.25}
        distortion={0.18}
        distortionScale={0.35}
        temporalDistortion={0.06}
        backside={spec.backside}
        backsideThickness={0.5}
        samples={spec.samples}
        resolution={spec.resolution}
        color={tint}
        attenuationColor={tint}
        attenuationDistance={8}
      />
    </mesh>
  );
}

function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function Motes({ count = 90, color }: { count?: number; color: string }) {
  const ref = React.useRef<THREE.Points>(null);

  const { positions, speeds } = React.useMemo(() => {
    const rand = mulberry32(1337);
    const pos = new Float32Array(count * 3);
    const spd = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (rand() - 0.5) * 18;
      pos[i * 3 + 1] = (rand() - 0.5) * 11;
      pos[i * 3 + 2] = (rand() - 0.5) * 6 - 1;
      spd[i] = 0.02 + rand() * 0.05;
    }
    return { positions: pos, speeds: spd };
  }, [count]);

  useFrame((_, delta) => {
    const pts = ref.current;
    if (!pts) return;
    const attr = pts.geometry.getAttribute("position") as THREE.BufferAttribute;
    const arr = attr.array as Float32Array;
    for (let i = 0; i < count; i++) {
      arr[i * 3 + 1] += speeds[i] * delta;
      if (arr[i * 3 + 1] > 5.5) arr[i * 3 + 1] = -5.5;
    }
    attr.needsUpdate = true;
  });

  return (
    <points ref={ref} frustumCulled={false}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} count={count} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial size={0.045} color={color} transparent opacity={0.5} sizeAttenuation depthWrite={false} />
    </points>
  );
}

function FocalGroup({ children }: { children: React.ReactNode }) {
  const { viewport } = useThree();
  const portrait = viewport.width < viewport.height;
  return <group position={[0, portrait ? 0.5 : 0.62, portrait ? -0.6 : 0]}>{children}</group>;
}

function Scene({
  headline,
  headlineColor,
  displayFont,
  italic,
  progress,
  reducedMotion,
  dispersion,
  tint,
  moteColor,
  spec,
}: {
  headline: string;
  headlineColor: string;
  displayFont: string;
  italic: boolean;
  progress: React.RefObject<number>;
  reducedMotion: boolean;
  dispersion: number;
  tint: string;
  moteColor: string;
  spec: QualitySpec;
}) {
  const texture = useHeadlineTexture(headline, headlineColor, displayFont, italic);

  return (
    <>
      <Environment resolution={256}>
        <Lightformer intensity={5} position={[0, 5, 4]} scale={[12, 4, 1]} color="#fff6e2" />
        <Lightformer intensity={3.2} position={[-6, 1, 3]} scale={[4, 9, 1]} color="#bcd6ff" />
        <Lightformer intensity={2.6} position={[6, -2, 2]} scale={[5, 6, 1]} color="#ffcf96" />
        <Lightformer intensity={1.8} position={[0, -4, -3]} scale={[9, 3, 1]} color="#ffffff" />
      </Environment>

      <FocalGroup>
        <Headline texture={texture} />
        <Crystal progress={progress} reducedMotion={reducedMotion} dispersion={dispersion} tint={tint} spec={spec} />
      </FocalGroup>
      <Motes color={moteColor} count={spec.motes} />
    </>
  );
}

type Quality = "low" | "medium" | "high";

interface QualitySpec {
  samples: number;
  resolution: number;
  motes: number;
  backside: boolean;
  maxDpr: number;
}

const QUALITY: Record<Quality, QualitySpec> = {
  low: { samples: 3, resolution: 192, motes: 30, backside: false, maxDpr: 1.25 },
  medium: { samples: 4, resolution: 256, motes: 55, backside: true, maxDpr: 1.5 },
  high: { samples: 6, resolution: 512, motes: 90, backside: true, maxDpr: 1.75 },
};

function subscribeToViewport(cb: () => void) {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
}

function detectQuality(): Quality {
  if (typeof window === "undefined") return "medium";
  const cores = navigator.hardwareConcurrency ?? 4;
  const w = window.innerWidth;
  if (w < 768 || cores <= 4) return "low";
  if (w < 1440 || cores <= 8) return "medium";
  return "high";
}

const ENTER = {
  hidden: { opacity: 0, y: 18 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 96, damping: 17, mass: 0.9 },
  },
};

const GROUP = {
  hidden: {},
  show: { transition: { staggerChildren: 0.11, delayChildren: 0.15 } },
};

export interface PrismHeroProps {
  eyebrow?: string;
  headline?: string;
  description?: string;
  action?: React.ReactNode;
  secondaryAction?: React.ReactNode;
  meta?: string[];
  dispersion?: number;
  tint?: string;
  background?: string;
  foreground?: string;
  accent?: string;
  displayFont?: string;
  italicHeadline?: boolean;
  staticProgress?: number;
  sceneChildren?: React.ReactNode;
  topInset?: boolean;
  className?: string;
}

export function PrismHero({
  eyebrow = "Bevel UI",
  headline = "Refraction",
  description = "A faceted crystal with real transmission and chromatic dispersion, refracting the headline behind it. No models, no HDRI, no external assets.",
  action,
  secondaryAction,
  meta = ["Procedural geometry", "Real transmission", "Zero assets"],
  dispersion = 0.42,
  tint = "#ffffff",
  background = "#08080B",
  foreground = "#EDE8DF",
  accent = "#C9A961",
  displayFont = "var(--font-display), 'Bodoni Moda', Georgia, serif",
  italicHeadline = false,
  staticProgress,
  sceneChildren,
  topInset = false,
  className,
}: PrismHeroProps) {
  const sectionRef = React.useRef<HTMLDivElement>(null);
  const progress = React.useRef(0);
  const [reducedMotion, setReducedMotion] = React.useState(false);
  const [ready, setReady] = React.useState(false);
  const prefersReduced = useReducedMotion();
  const controls = useAnimationControls();

  const quality = React.useSyncExternalStore(subscribeToViewport, detectQuality, () => "medium" as Quality);
  const spec = QUALITY[quality];

  const stageRef = React.useRef<HTMLDivElement>(null);
  const [onScreen, setOnScreen] = React.useState(true);

  React.useEffect(() => {
    const el = stageRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      ([entry]) => setOnScreen(entry.isIntersecting),
      { rootMargin: "120px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  React.useEffect(() => {
    if (prefersReduced || document.hidden) {
      controls.set("show");
      return;
    }
    controls.start("show");
  }, [controls, prefersReduced]);

  const railRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const raf = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReducedMotion(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  React.useEffect(() => {
    const paint = (p: number) => {
      progress.current = p;
      if (railRef.current) railRef.current.style.transform = `scaleX(${p})`;
    };

    if (staticProgress !== undefined) {
      paint(Math.min(1, Math.max(0, staticProgress)));
      return;
    }
    if (reducedMotion) {
      paint(0);
      return;
    }

    let raf = 0;
    const update = () => {
      raf = 0;
      const el = sectionRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const total = rect.height - window.innerHeight;
      paint(total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [reducedMotion, staticProgress]);

  const isStatic = staticProgress !== undefined;

  return (
    <div ref={sectionRef} className={["relative w-full", isStatic ? "h-screen" : "h-[260vh]", className].filter(Boolean).join(" ")} style={{ background }}>
      <div ref={stageRef} className="sticky top-0 h-screen w-full overflow-hidden">
        <div className="absolute inset-0 transition-opacity duration-[1200ms] ease-out" style={{ opacity: ready ? 1 : 0 }}>
          <Canvas
            frameloop={onScreen ? "always" : "never"}
            dpr={[1, spec.maxDpr]}
            gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
            camera={{ fov: 40, near: 0.1, far: 60, position: [0, 0, 7] }}
            onCreated={({ gl }) => gl.setClearColor(new THREE.Color(background), 1)}
          >
            <Scene
              headline={headline}
              headlineColor={foreground}
              displayFont={displayFont}
              italic={italicHeadline}
              progress={progress}
              reducedMotion={reducedMotion}
              dispersion={dispersion}
              tint={tint}
              moteColor={accent}
              spec={spec}
            />
            {sceneChildren}
          </Canvas>
        </div>

        <div aria-hidden className="pointer-events-none absolute inset-0" style={{ background: `radial-gradient(120% 90% at 50% 45%, transparent 40%, ${background} 100%)` }} />
        <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.16] mix-blend-overlay" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E\")" }} />

        <motion.div variants={GROUP} initial="hidden" animate={controls} className={`pointer-events-none absolute inset-0 flex flex-col px-5 sm:px-10 ${topInset ? "pb-8 pt-24 sm:pb-14 sm:pt-28" : "py-8 sm:py-14"}`}>
          <motion.div variants={ENTER} className="flex items-center gap-3">
            <span aria-hidden className="h-px w-8" style={{ background: accent, opacity: 0.7 }} />
            <span className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.32em]" style={{ color: accent }}>
              {eyebrow}
            </span>
          </motion.div>

          <div aria-hidden className="flex-1" />

          <div className="mx-auto w-full max-w-2xl text-center">
            <motion.p variants={ENTER} className="mx-auto max-w-md text-[13px] leading-relaxed sm:text-[15px]" style={{ color: foreground, opacity: 0.62 }}>
              {description}
            </motion.p>

            {(action || secondaryAction) && (
              <motion.div variants={ENTER} className="pointer-events-auto mt-6 flex flex-col items-center justify-center gap-3 sm:mt-8 sm:flex-row">
                {action}
                {secondaryAction}
              </motion.div>
            )}
          </div>

          <motion.div variants={ENTER} className="mt-8 flex flex-wrap items-center justify-between gap-4 sm:mt-14">
            <div className="hidden flex-wrap items-center gap-x-5 gap-y-2 sm:flex">
              {meta.map((m) => (
                <span key={m} className="font-[family-name:var(--font-mono)] text-[10px] uppercase tracking-[0.22em]" style={{ color: foreground, opacity: 0.6 }}>
                  {m}
                </span>
              ))}
            </div>

            {!isStatic && (
              <div className="h-px w-24 overflow-hidden" style={{ background: `${foreground}22` }}>
                <div ref={railRef} className="h-full origin-left" style={{ background: accent, transform: "scaleX(0)" }} />
              </div>
            )}
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}

export default PrismHero;
