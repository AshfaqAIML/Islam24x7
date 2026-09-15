"use client";

/**
 * Reader display settings — persisted to localStorage, read via
 * useSyncExternalStore (hydration-safe: SSR returns defaults).
 *
 * Settings apply to the reader surface only; they are device-local and
 * will sync with the account layer (P8).
 */

export type ReaderFontSize = "sm" | "md" | "lg" | "xl";
export type ReaderSpacing = "compact" | "normal" | "relaxed";
export type ReaderWidth = "narrow" | "medium" | "wide";
export type ReaderPaper = "default" | "sepia" | "ink";

export interface ReaderSettings {
  fontSize: ReaderFontSize;
  spacing: ReaderSpacing;
  width: ReaderWidth;
  paper: ReaderPaper;
}

export const defaultReaderSettings: ReaderSettings = {
  fontSize: "md",
  spacing: "normal",
  width: "medium",
  paper: "default",
};

const STORAGE_KEY = "ik.readerSettings.v1";
/** Stable identity — getServerSnapshot must never allocate (React caches it). */
const SERVER_SNAPSHOT: ReaderSettings = Object.freeze({ ...defaultReaderSettings });

let hydrated = false;
let settings: ReaderSettings = { ...defaultReaderSettings };
let snapshot: ReaderSettings = { ...defaultReaderSettings };
const listeners = new Set<() => void>();

function emit() {
  snapshot = { ...settings };
  listeners.forEach((l) => l());
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // storage unavailable — degrade gracefully
  }
}

function sanitize(raw: unknown): ReaderSettings {
  const s = { ...defaultReaderSettings };
  if (raw && typeof raw === "object") {
    const r = raw as Partial<ReaderSettings>;
    if (["sm", "md", "lg", "xl"].includes(r.fontSize ?? "")) {
      s.fontSize = r.fontSize as ReaderFontSize;
    }
    if (["compact", "normal", "relaxed"].includes(r.spacing ?? "")) {
      s.spacing = r.spacing as ReaderSpacing;
    }
    if (["narrow", "medium", "wide"].includes(r.width ?? "")) {
      s.width = r.width as ReaderWidth;
    }
    if (["default", "sepia", "ink"].includes(r.paper ?? "")) {
      s.paper = r.paper as ReaderPaper;
    }
  }
  return s;
}

function init() {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    settings = raw ? sanitize(JSON.parse(raw)) : { ...defaultReaderSettings };
  } catch {
    settings = { ...defaultReaderSettings };
  }
  snapshot = { ...settings };
}

function update(patch: Partial<ReaderSettings>) {
  init();
  settings = sanitize({ ...settings, ...patch });
  persist();
  emit();
}

/** Tailwind class maps shared by the reader surface. */
export const readerTypography: Record<
  ReaderFontSize,
  { cls: string; label: string }
> = {
  sm: { cls: "text-[15px]", label: "Small" },
  md: { cls: "text-[17px]", label: "Medium" },
  lg: { cls: "text-[19px]", label: "Large" },
  xl: { cls: "text-[22px]", label: "X-Large" },
};

export const readerSpacing: Record<
  ReaderSpacing,
  { cls: string; label: string }
> = {
  compact: { cls: "leading-[1.65]", label: "Compact" },
  normal: { cls: "leading-[1.85]", label: "Normal" },
  relaxed: { cls: "leading-[2.1]", label: "Relaxed" },
};

export const readerWidth: Record<ReaderWidth, { cls: string; label: string }> = {
  narrow: { cls: "max-w-[38rem]", label: "Narrow" },
  medium: { cls: "max-w-[44rem]", label: "Medium" },
  wide: { cls: "max-w-[52rem]", label: "Wide" },
};

export const readerPaper: Record<ReaderPaper, { label: string }> = {
  default: { label: "Standard" },
  sepia: { label: "Sepia" },
  ink: { label: "Ink" },
};

export const readerSettingsStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): ReaderSettings {
    init();
    return snapshot;
  },
  getServerSnapshot(): ReaderSettings {
    return SERVER_SNAPSHOT;
  },
  setFontSize(v: ReaderFontSize) {
    update({ fontSize: v });
  },
  setSpacing(v: ReaderSpacing) {
    update({ spacing: v });
  },
  setWidth(v: ReaderWidth) {
    update({ width: v });
  },
  setPaper(v: ReaderPaper) {
    update({ paper: v });
  },
  reset() {
    update({ ...defaultReaderSettings });
  },
};
