"use client";

/**
 * Recent search queries — external store over localStorage, read via
 * useSyncExternalStore (hydration-safe, cross-page sync, lint-clean).
 * Local-only by design: search history is personal data and stays on the
 * device until the personal layer (P8) introduces optional sync.
 */

const STORAGE_KEY = "ik.search-history.v1";
const MAX_ITEMS = 8;
/** Stable identity — getServerSnapshot must never allocate (React caches it). */
const EMPTY_HISTORY: readonly string[] = Object.freeze([]);

let hydrated = false;
let items: string[] = [];
/** Frozen snapshot for useSyncExternalStore referential stability. */
let snapshot: readonly string[] = Object.freeze([]);

const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // storage unavailable — degrade gracefully
  }
}

function commit(next: string[]) {
  items = next;
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
    items = Array.isArray(parsed)
      ? parsed.filter((x) => typeof x === "string" && x.trim().length > 0).slice(0, MAX_ITEMS)
      : [];
  } catch {
    items = [];
  }
  snapshot = Object.freeze([...items]);
}

/** Normalize for dedupe/storage: trimmed, single-spaced, case-folded identity. */
function normalize(q: string): string {
  return q.trim().replace(/\s+/g, " ").toLowerCase();
}

/** Display form: trimmed, single-spaced, original casing. */
function displayForm(q: string): string {
  return q.trim().replace(/\s+/g, " ");
}

export const searchHistoryStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): readonly string[] {
    init();
    return snapshot;
  },
  getServerSnapshot(): readonly string[] {
    return EMPTY_HISTORY;
  },
  /** Record a query (most-recent first, deduped, capped at MAX_ITEMS). */
  add(rawQuery: string) {
    const query = displayForm(rawQuery);
    if (query.length < 2) return;
    init();
    const identity = normalize(query);
    const next = [query, ...items.filter((x) => normalize(x) !== identity)];
    commit(next.slice(0, MAX_ITEMS));
  },
  remove(rawQuery: string) {
    init();
    const identity = normalize(rawQuery);
    commit(items.filter((x) => normalize(x) !== identity));
  },
  clear() {
    commit([]);
  },
};
