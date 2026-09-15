"use client";

/**
 * Quick-dhikr (Tasbeeh preview) counter — external store over localStorage,
 * read via useSyncExternalStore so it is hydration-safe and lint-clean
 * (no setState-in-effect, same pattern as apk-prompt-store).
 *
 * This is real functionality (a plain counter — no religious content is
 * generated); the full Azkar/Tasbeeh module with routines lands in Phase 10.
 */

const STORAGE_KEY = "ik.quickDhikr.v1";
const DAILY_TARGET = 33;

let hydrated = false;
let count = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(count));
  } catch {
    // storage unavailable — degrade gracefully
  }
}

function init() {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw == null ? Number.NaN : Number(raw);
    count = Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : 0;
  } catch {
    count = 0;
  }
}

function update(mutate: (prev: number) => number) {
  init();
  count = Math.max(0, mutate(count));
  persist();
  emit();
}

export const dhikrStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): number {
    init();
    return count;
  },
  getServerSnapshot(): number {
    return 0;
  },
  increment() {
    update((n) => n + 1);
  },
  reset() {
    update(() => 0);
  },
  /** Daily target used by the progress ring (33 — the common tasbeeh count). */
  dailyTarget(): number {
    return DAILY_TARGET;
  },
};
