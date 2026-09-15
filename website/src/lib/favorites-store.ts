"use client";

/**
 * Book favorites — external store over localStorage, read via
 * useSyncExternalStore (hydration-safe, cross-page sync, lint-clean).
 * Local-only for now; account sync arrives with the personal layer (P8).
 */

const STORAGE_KEY = "ik.favorites.v1";
/** Stable identity — getServerSnapshot must never allocate (React caches it). */
const EMPTY_FAVORITES: readonly string[] = Object.freeze([]);

let hydrated = false;
let favorites: string[] = [];
/** Frozen snapshot for useSyncExternalStore referential stability. */
let snapshot: readonly string[] = Object.freeze([]);

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites));
  } catch {
    // storage unavailable — degrade gracefully
  }
}

function commit(next: string[]) {
  favorites = next;
  snapshot = Object.freeze([...next]);
  persist();
  emit();
}

function init() {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw == null ? [] : JSON.parse(raw);
    favorites = Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    favorites = [];
  }
  snapshot = Object.freeze([...favorites]);
}

export const favoritesStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): readonly string[] {
    init();
    return snapshot;
  },
  getServerSnapshot(): readonly string[] {
    return EMPTY_FAVORITES;
  },
  has(id: string): boolean {
    init();
    return favorites.includes(id);
  },
  toggle(id: string): boolean {
    init();
    if (favorites.includes(id)) {
      commit(favorites.filter((x) => x !== id));
      return false;
    }
    commit([id, ...favorites]);
    return true;
  },
  remove(id: string) {
    init();
    if (favorites.includes(id)) commit(favorites.filter((x) => x !== id));
  },
  clear() {
    commit([]);
  },
};
