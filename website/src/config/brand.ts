/**
 * Brand configuration — the single source of truth for identity.
 * Replace values here (or via env) to re-brand the whole product.
 * No component should hard-code the brand name.
 */
export const brand = {
  /** Full product name. Configurable — change here to re-brand the product. */
  name: "Islam24x7",
  /** Compact name for icons / tight spaces. */
  shortName: "Islam24x7",
  /** Provisional tagline — may change. */
  tagline: "Read. Search. Learn. Explore.",
  description:
    "Islam24x7 — a modern Islamic knowledge platform: Quran, Hadith, a structured Islamic library, and an AI research assistant grounded in verified sources.",
  /** One-line benefits used by the APK prompt / store-style surfaces. */
  benefits: [
    "Read Quran",
    "Explore Hadith",
    "Read Islamic Books",
    "Search Islamic Knowledge",
    "Use Islam24x7 Offline",
  ],
  /** Key theme colors mirrored from globals.css — used for manifest/meta. */
  themeColorLight: "#f8f6ef",
  themeColorDark: "#10201c",
  themeColor: "#0d4d3a",
  gold: "#c9a227",
  /** Social paths */
  ogImage: "/icons/og-image.jpg",
  appIcon: "/icons/icon-512.png",
} as const;

export type Brand = typeof brand;
