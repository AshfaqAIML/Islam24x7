"use client";

import { useSyncExternalStore } from "react";
import {
  readerSettingsStore,
  readerTypography,
  readerSpacing,
  readerWidth,
  type ReaderSettings,
} from "@/lib/reader-settings-store";

export function useReaderSettings(): ReaderSettings {
  return useSyncExternalStore(
    readerSettingsStore.subscribe,
    readerSettingsStore.getSnapshot,
    readerSettingsStore.getServerSnapshot
  );
}

/** Resolved Tailwind classes for the current settings. */
export function useReaderTypography() {
  const s = useReaderSettings();
  return {
    settings: s,
    fontClass: readerTypography[s.fontSize].cls,
    spacingClass: readerSpacing[s.spacing].cls,
    widthClass: readerWidth[s.width].cls,
    /** Paper surface classes for the article container. */
    paperClass:
      s.paper === "sepia"
        ? "bg-[#f4ead6] text-stone-900 dark:bg-[#f4ead6] dark:text-stone-900 selection:bg-amber-700/25"
        : s.paper === "ink"
          ? "bg-stone-950 text-stone-100 selection:bg-primary/40"
          : "bg-card text-foreground",
  };
}
