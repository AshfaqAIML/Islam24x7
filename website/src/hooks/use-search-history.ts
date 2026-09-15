"use client";

import { useSyncExternalStore } from "react";
import { searchHistoryStore } from "@/lib/search-history-store";

/** Recent search queries (hydration-safe, device-local). */
export function useSearchHistory(): {
  items: readonly string[];
  add: (q: string) => void;
  remove: (q: string) => void;
  clear: () => void;
} {
  const items = useSyncExternalStore(
    searchHistoryStore.subscribe,
    searchHistoryStore.getSnapshot,
    searchHistoryStore.getServerSnapshot
  );
  return {
    items,
    add: searchHistoryStore.add,
    remove: searchHistoryStore.remove,
    clear: searchHistoryStore.clear,
  };
}
