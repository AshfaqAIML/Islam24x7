"use client";

import { useSyncExternalStore } from "react";
import {
  readingProgressStore,
  type ReadingProgressRecord,
} from "@/lib/reading-progress-store";

/** All progress records, newest first (hydration-safe). */
export function useAllReadingProgress(): readonly ReadingProgressRecord[] {
  return useSyncExternalStore(
    readingProgressStore.subscribe,
    readingProgressStore.getSnapshot,
    readingProgressStore.getServerSnapshot
  );
}

/** Progress for one book (hydration-safe; null on server). */
export function useReadingProgress(
  bookId: string
): ReadingProgressRecord | null {
  const all = useAllReadingProgress();
  return all.find((r) => r.bookId === bookId) ?? null;
}
