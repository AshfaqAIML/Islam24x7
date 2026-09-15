/**
 * ⚠️ DEMO PAGE CONTENT — clearly-labeled placeholder text. ⚠️
 *
 * STRICT RULE: these paragraphs contain NO Quran, hadith, rulings or
 * quotations. They exist purely so the reader experience (typography,
 * pagination, settings, progress) can be reviewed before the Knowledge
 * Base connects. Every reader surface displays a Demo indicator and a
 * provenance note.
 */
import type { BookPage } from "@/types/knowledge-base";
import { demoBooks, demoChaptersFor } from "@/lib/demo/books";

const PARAGRAPHS = [
  "This is placeholder page content. When the Knowledge Base connects, this area renders the authentic text of the volume exactly as prepared by the ingestion pipeline — with verse and hadith citations linked to their sources.",
  "The reader is designed for long, comfortable study sessions: adjustable type size, line spacing and measure, three paper themes, and a progress marker that remembers exactly where you stopped.",
  "Structure preview: each chapter divides into pages, each page flows as readable paragraphs, and every passage will be addressable by a stable citation (book → chapter → page) once real content arrives.",
  "Nothing on this page imitates any real Islamic work. The title, author and chapter labels are placeholders, clearly marked with a Demo badge on every reader surface.",
  "Deep links land here: /library/{bookId}/read opens the volume, and a chapter or page reference takes you straight to the exact spot — the same anchor the AI assistant will use to cite its sources.",
];

/** Deterministic placeholder pages for one chapter of a demo book. */
export function demoPagesFor(bookId: string, chapterId?: string): BookPage[] {
  const book = demoBooks.find((b) => b.id === bookId);
  if (!book) return [];
  const chapters = demoChaptersFor(bookId);
  const chapter = chapterId
    ? chapters.find((c) => c.id === chapterId)
    : chapters[0];
  if (!chapter) return [];

  const pageCount = Math.max(3, Math.round((chapter.pageCount ?? 12) / 6));
  return Array.from({ length: pageCount }, (_, i) => {
    // Rotate the paragraph set deterministically so every page differs.
    const rotated = [...PARAGRAPHS.slice(i % PARAGRAPHS.length), ...PARAGRAPHS.slice(0, i % PARAGRAPHS.length)];
    const picked = rotated.slice(0, 3 + (i % 2));
    return {
      id: `${chapter.id}-p-${i + 1}`,
      bookId: book.id,
      chapterId: chapter.id,
      pageNumber: i + 1,
      content: picked.join("\n\n"),
    };
  });
}
