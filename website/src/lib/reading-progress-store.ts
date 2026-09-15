"use client";

/**
 * Reading progress — one record per book, persisted locally, read via
 * useSyncExternalStore. Powers the "Continue reading" card on Home and the
 * resume banner in the reader. Account sync arrives with P8.
 */

export interface ReadingProgressRecord {
  bookId: string;
  bookTitle?: string;
  chapterId?: string;
  chapterTitle?: string;
  page?: number;
  pageCount?: number;
  /** 0–100 within the current chapter. */
  percent: number;
  updatedAt: number;
}

const STORAGE_KEY = "ik.readingProgress.v1";
const MAX_BOOKS = 50;
const EMPTY_RECORDS: readonly ReadingProgressRecord[] = Object.freeze([]);

let hydrated = false;
let records: Record<string, ReadingProgressRecord> = {};
let snapshot: readonly ReadingProgressRecord[] = [];
const listeners = new Set<() => void>();

function emit() {
  snapshot = Object.values(records).sort((a, b) => b.updatedAt - a.updatedAt);
  listeners.forEach((l) => l());
}

function persist() {
  try {
    const trimmed = Object.fromEntries(
      Object.values(records)
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, MAX_BOOKS)
        .map((r) => [r.bookId, r])
    );
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // storage unavailable — degrade gracefully
  }
}

function init() {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, ReadingProgressRecord>) : {};
    records = {};
    for (const r of Object.values(parsed)) {
      if (r && typeof r.bookId === "string" && typeof r.percent === "number") {
        records[r.bookId] = r;
      }
    }
  } catch {
    records = {};
  }
  emit();
}

export const readingProgressStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): readonly ReadingProgressRecord[] {
    init();
    return snapshot;
  },
  getServerSnapshot(): readonly ReadingProgressRecord[] {
    return EMPTY_RECORDS;
  },
  get(bookId: string): ReadingProgressRecord | null {
    init();
    return records[bookId] ?? null;
  },
  save(record: Omit<ReadingProgressRecord, "updatedAt">) {
    init();
    const prev = records[record.bookId];
    // Don't clobber a newer record with an older scroll event (out-of-order).
    if (prev && prev.percent > record.percent + 0.5 && record.percent < 1) {
      if (Date.now() - prev.updatedAt < 4_000) return;
    }
    records[record.bookId] = { ...record, updatedAt: Date.now() };
    persist();
    emit();
  },
  clear(bookId: string) {
    init();
    if (records[bookId]) {
      delete records[bookId];
      persist();
      emit();
    }
  },
};
