import { useRef, useState, type ReactNode } from "react";
import MuteToggle from "./MuteToggle";
import { play } from "@/audio/useSound";

interface BubbleState {
  id: number;
  left: string;
  top: string;
  size: number;
  delay: number;
  duration: number;
  phase: "stationary" | "rising" | "parked" | "popping";
  poppedFrom?: "stationary" | "rising" | "parked";
}

// Fixed positions (no randomness) so server and client render identically.
const INITIAL_BUBBLES: BubbleState[] = [
  { left: "6%", top: "14%", size: 90, delay: 0 },
  { left: "18%", top: "62%", size: 46, delay: 1.5 },
  { left: "30%", top: "30%", size: 28, delay: 3 },
  { left: "52%", top: "8%", size: 60, delay: 2 },
  { left: "70%", top: "55%", size: 110, delay: 0.8 },
  { left: "88%", top: "28%", size: 40, delay: 2.6 },
  { left: "92%", top: "75%", size: 70, delay: 1.1 },
  { left: "42%", top: "78%", size: 34, delay: 3.4 },
].map((b, i) => ({ ...b, id: i, duration: 0, phase: "stationary" as const }));

export default function Scene({
  children,
  interactive = false,
}: {
  children: ReactNode;
  /** Bubbles can be popped (main menu only). */
  interactive?: boolean;
}) {
  const [bubbles, setBubbles] = useState<BubbleState[]>(INITIAL_BUBBLES);
  const nextId = useRef(INITIAL_BUBBLES.length);

  // A new bubble that floats up from below the screen. Only called from
  // client events, so using Math.random here is safe for hydration.
  function spawnRising(): BubbleState {
    return {
      id: nextId.current++,
      left: `${5 + Math.random() * 90}%`,
      top: `${10 + Math.random() * 62}%`,
      size: 30 + Math.random() * 90,
      delay: 0,
      duration: 9 + Math.random() * 7,
      phase: "rising",
    };
  }

  function pop(id: number) {
    if (!interactive) return;
    const target = bubbles.find((b) => b.id === id);
    if (!target || target.phase === "popping") return;
    const poppedFrom = target.phase;
    play("menu.bubblePop");
    setBubbles((list) => list.map((b) => (b.id === id ? { ...b, phase: "popping", poppedFrom } : b)));
  }

  function onAnimationEnd(b: BubbleState, animationName: string) {
    if (animationName === "bubble-pop" && b.phase === "popping") {
      setBubbles((list) => list.map((x) => (x.id === b.id ? spawnRising() : x)));
    } else if (animationName === "bubble-rise" && b.phase === "rising") {
      setBubbles((list) => list.map((x) => (x.id === b.id ? { ...x, phase: "parked" } : x)));
    }
  }

  return (
    <div className="aero-scene">
      {bubbles.map((b) => (
        <span
          key={b.id}
          className={`bubble${interactive ? " interactive" : ""}${b.phase === "rising" || (b.phase === "popping" && b.poppedFrom === "rising") ? " rising" : ""}${b.phase !== "rising" && b.poppedFrom !== "rising" ? " bobbing" : ""}`}
          style={{
            left: b.left,
            top: b.top,
            width: b.size,
            height: b.size,
            animationDelay: `${b.delay}s`,
            ...(b.phase === "rising" || (b.phase === "popping" && b.poppedFrom === "rising") ? { animationDuration: `${b.duration}s` } : null),
          }}
          onAnimationEnd={(e) => {
            if (e.target === e.currentTarget) onAnimationEnd(b, e.animationName);
          }}
          onPointerDown={() => pop(b.id)}
        >
          <span
            className={`bubble-orb${b.phase === "popping" ? " popping" : ""}`}
            onAnimationEnd={(e) => {
              if (e.target === e.currentTarget) onAnimationEnd(b, e.animationName);
            }}
          />
        </span>
      ))}
      <div className={`aero-content${interactive ? " passthrough" : ""}`}>{children}</div>
      <MuteToggle />
    </div>
  );
}
