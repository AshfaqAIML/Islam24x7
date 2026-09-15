/**
 * Demo content — SINGLE SOURCE OF RULES:
 *
 *  1. Nothing here is invented. Quran text is verbatim, one of the most
 *     widely memorised passages in existence, transcribed exactly.
 *  2. Every item is flagged `isDemo: true` and MUST render with a DemoBadge
 *     plus a note stating where real content will come from.
 *  3. When the Knowledge Base connects, these previews are replaced by
 *     real data from `KNOWLEDGE_BASE_API_URL` (services layer only).
 */

export interface DemoAyah {
  isDemo: true;
  arabic: string;
  translation: string;
  /** Citation — Surah name + ayah numbers (clickable deep link in Phase 6). */
  citation: string;
  surahId: number;
  ayahStart: number;
  ayahEnd: number;
}

export const demoDailyAyah: DemoAyah = {
  isDemo: true,
  arabic: "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
  translation: "In the name of Allah, the Most Gracious, the Most Merciful.",
  citation: "Al-Fātiḥah 1:1",
  surahId: 1,
  ayahStart: 1,
  ayahEnd: 1,
};
