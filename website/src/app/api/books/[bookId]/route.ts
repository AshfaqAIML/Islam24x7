import { NextResponse } from "next/server";
import { getBook } from "@/services/books";

/** GET /api/books/:bookId */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ bookId: string }> }
) {
  const { bookId } = await params;
  try {
    const book = await getBook(bookId);
    if (!book) {
      return NextResponse.json({ error: "Book not found." }, { status: 404 });
    }
    return NextResponse.json(book);
  } catch (error) {
    console.error("[api/books/:id] failed:", error);
    return NextResponse.json(
      { error: "Unable to load this book right now." },
      { status: 502 }
    );
  }
}
