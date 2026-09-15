import { brand } from "@/config/brand";

/**
 * Site-level configuration: routes, navigation, feature flags.
 */

export type NavItem = {
  label: string;
  href: string;
  /** Module not shipped yet — rendered as disabled with a "Soon" chip. */
  soon?: boolean;
  /** Phase in which the module is planned (used for honest UI during construction). */
  phase?: number;
};

export type TabItem = {
  key: string;
  label: string;
  /** Lucide icon name shared with home module grid maps. */
  icon: "home" | "book-open-text" | "search" | "library" | "sparkles" | "menu";
  href?: string;
  /** Opens the More sheet instead of navigating. */
  action?: "more";
  soon?: boolean;
  phase?: number;
};

export const routes = {
  home: "/",
  download: "/download",
  // Planned routes (implemented in later phases — never linked as active):
  library: "/library",
  quran: "/quran",
  hadith: "/hadith",
  search: "/search",
  ai: "/ai",
  duas: "/duas",
  azkar: "/azkar",
  prayer: "/prayer",
  qibla: "/qibla",
  tasbeeh: "/tasbeeh",
  more: "/more",
} as const;

export const mainNav: NavItem[] = [
  { label: "Home", href: routes.home },
  { label: "Library", href: routes.library },
  { label: "Search", href: routes.search },
  { label: "Ask AI", href: routes.ai },
  { label: "Quran", href: routes.quran, soon: true, phase: 6 },
  { label: "Hadith", href: routes.hadith, soon: true, phase: 7 },
];

/**
 * Mobile bottom tab bar (Phase 2). Exactly five slots, thumb-reachable;
 * modules that have not shipped yet stay visible but clearly "Soon".
 * Layout per the product shell spec: Home · Quran · Library · Ask AI · More
 * (Search lives in the header, always one tap away).
 */
export const tabNav: TabItem[] = [
  { key: "home", label: "Home", icon: "home", href: routes.home },
  { key: "quran", label: "Quran", icon: "book-open-text", soon: true, phase: 6 },
  { key: "library", label: "Library", icon: "library", href: routes.library },
  { key: "ai", label: "Ask AI", icon: "sparkles", href: routes.ai },
  { key: "more", label: "More", icon: "menu", action: "more" },
];

/**
 * Build status — drives the honest phase-progress indicator on Home.
 * Keep in sync with docs/ARCHITECTURE.md §6.
 */
export const buildProgress = {
  currentPhase: 5,
  totalPhases: 16,
  phaseLabel: "Global search",
} as const;

/**
 * Modules showcased on the Phase-1 home page.
 * Status is honest: planned phases, no fake content behind them.
 */
export const moduleShowcase = [
  {
    key: "quran",
    title: "Quran",
    description: "Surahs, ayah-by-ayah reading, translations, bookmarks.",
    icon: "book-open-text",
    phase: 6,
  },
  {
    key: "hadith",
    title: "Hadith",
    description: "Collections → books → chapters, with grading where reliable.",
    icon: "scroll-text",
    phase: 7,
  },
  {
    key: "library",
    title: "Library",
    description: "Fiqh, Tafsir, Aqeedah, Seerah, history — browse and read.",
    icon: "library",
    phase: 3,
    live: true,
    href: "/library",
  },
  {
    key: "reader",
    title: "Reader",
    description: "A premium e-book reader with highlights, notes and progress.",
    icon: "book-marked",
    phase: 4,
    live: true,
    href: "/library/demo-seerah-1/read",
  },
  {
    key: "search",
    title: "Global Search",
    description: "One search across Quran, Hadith and the whole library.",
    icon: "search",
    phase: 5,
    live: true,
    href: "/search",
  },
  {
    key: "ai",
    title: "AI Assistant",
    description:
      "Ask-the-library foundation is live — every answer will cite its sources.",
    icon: "sparkles",
    phase: 9,
    live: true,
    href: "/ai",
  },
  {
    key: "duas",
    title: "Duas & Azkar",
    description: "Morning & evening remembrance with counters and routines.",
    icon: "hand-heart",
    phase: 10,
  },
  {
    key: "prayer",
    title: "Prayer, Qibla & Tasbeeh",
    description: "Prayer times, Qibla compass, dhikr counter, Hijri calendar.",
    icon: "compass",
    phase: 11,
  },
] as const;

export const featureFlags = {
  /**
   * Mock/demo mode. When true, services return clearly-labeled placeholder
   * data and the UI shows a demo indicator. Real content always comes from
   * the Knowledge Base backend once connected.
   */
  useMockData: process.env.NEXT_PUBLIC_USE_MOCK_DATA === "true",
} as const;

export const siteConfig = {
  /** Canonical site URL (used for SEO metadata; set in production). */
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  name: brand.name,
} as const;
