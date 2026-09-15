import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getBook, getBookChapters } from "@/services/books";
import { ReaderView } from "@/components/reader/reader-view";

interface PageProps {
  params: Promise<{ bookId: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { bookId } = await params;
  const book = await getBook(bookId);
  if (!book) return { title: "Book not found" };
  return {
    title: `Reading — ${book.title}`,
    description: "Reader preview with labeled demo pages.",
    robots: { index: false },
  };
}

export default async function ReadPage({ params }: PageProps) {
  const { bookId } = await params;
  const [book, chapters] = await Promise.all([
    getBook(bookId),
    getBookChapters(bookId),
  ]);
  if (!book) notFound();

  return (
    <main className="flex-1">
      <ReaderView book={book} chapters={chapters} />
    </main>
  );
}
