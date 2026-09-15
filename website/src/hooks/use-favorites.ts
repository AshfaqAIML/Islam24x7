"use client";

import { useSyncExternalStore } from "react";
import { favoritesStore } from "@/lib/favorites-store";

/** All favorite book ids (hydration-safe). */
export function useFavorites(): readonly string[] {
  return useSyncExternalStore(
    favoritesStore.subscribe,
    favoritesStore.getSnapshot,
    favoritesStore.getServerSnapshot
  );
}

/** Reactive membership check for one book. */
export function useIsFavorite(bookId: string): boolean {
  const favorites = useFavorites();
  return favorites.includes(bookId);
}
