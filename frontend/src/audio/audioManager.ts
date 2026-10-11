import { SOUNDS, type SoundKey } from "./soundConfig";

// Browser-only audio playback. Safe to import anywhere; every function is a
// no-op on the server and for keys whose `src` is null in soundConfig.ts.

const MUTE_STORAGE_KEY = "bankroll.muted";

let initialized = false;
let muted = false;
let unlocked = false; // browsers block audio until the first user gesture
let desiredBgm: SoundKey | null = null;
let currentBgm: SoundKey | null = null;
let bgmEl: HTMLAudioElement | null = null;
const listeners = new Set<() => void>();

const clamp = (v: number) => Math.min(1, Math.max(0, v));

function init() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;
  try {
    muted = window.localStorage.getItem(MUTE_STORAGE_KEY) === "1";
  } catch {
    // storage unavailable; keep default
  }
  const unlock = () => {
    unlocked = true;
    applyBgm();
  };
  window.addEventListener("pointerdown", unlock, { once: true });
  window.addEventListener("keydown", unlock, { once: true });
}

function fade(el: HTMLAudioElement, to: number, ms: number, done?: () => void) {
  const from = el.volume;
  const start = performance.now();
  const tick = () => {
    const p = Math.min(1, (performance.now() - start) / ms);
    el.volume = clamp(from + (to - from) * p);
    if (p < 1) requestAnimationFrame(tick);
    else done?.();
  };
  requestAnimationFrame(tick);
}

function applyBgm() {
  if (!unlocked || typeof window === "undefined") return;

  if (desiredBgm !== currentBgm) {
    const old = bgmEl;
    if (old) fade(old, 0, 400, () => old.pause());
    bgmEl = null;
    currentBgm = desiredBgm;
    const def = desiredBgm ? SOUNDS[desiredBgm] : null;
    if (def?.src) {
      const el = new Audio(def.src);
      el.loop = true;
      // `loop` already restarts the file; this is a fallback for any player that reports "ended" anyway.
      el.addEventListener("ended", () => {
        el.currentTime = 0;
        if (!muted) void el.play().catch(() => {});
      });
      el.volume = 0;
      bgmEl = el;
      if (!muted) {
        void el.play().catch(() => {});
        fade(el, clamp(def.volume), 600);
      }
    }
  } else if (bgmEl && currentBgm) {
    if (muted) {
      bgmEl.pause();
    } else {
      bgmEl.volume = clamp(SOUNDS[currentBgm].volume);
      void bgmEl.play().catch(() => {});
    }
  }
}

/** Play a one-shot sound effect. */
export function play(key: SoundKey) {
  init();
  if (muted || typeof window === "undefined") return;
  const def = SOUNDS[key];
  if (!def.src) return;
  const el = new Audio(def.src);
  el.volume = clamp(def.volume);
  void el.play().catch(() => {});
}

/** Switch looping background music (crossfades). Pass null to stop. */
export function playBgm(key: SoundKey | null) {
  init();
  desiredBgm = key;
  applyBgm();
}

export function getMuted() {
  init();
  return muted;
}

export function setMuted(value: boolean) {
  init();
  muted = value;
  try {
    window.localStorage.setItem(MUTE_STORAGE_KEY, value ? "1" : "0");
  } catch {
    // ignore
  }
  applyBgm();
  listeners.forEach((l) => l());
}

export function subscribeMuted(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
