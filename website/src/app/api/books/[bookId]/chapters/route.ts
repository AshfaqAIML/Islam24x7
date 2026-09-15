import { NextResponse } from "next/server";
import { getBookChapters } from "@/services/books";

/** GET /api/books/:bookId/chapters */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ bookId: string }> }
) {
  const { bookId } = await params;
  try {
    const chapters = await getBookChapters(bookId);
    return NextResponse.json(chapters);
  } catch (error) {
    console.error("[api/books/:id/chapters] failed:", error);
    return NextResponse.json(
      { error: "Unable to load chapters right now." },
      { status: 502 }
    );
  }
}
