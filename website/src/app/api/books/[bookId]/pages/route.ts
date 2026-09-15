import { NextRequest, NextResponse } from "next/server";
import { getBookPages } from "@/services/books";

/** GET /api/books/:bookId/pages?chapterId= */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ bookId: string }> }
) {
  const { bookId } = await params;
  const chapterId = request.nextUrl.searchParams.get("chapterId") ?? undefined;
  try {
    const result = await getBookPages(bookId, chapterId);
    return NextResponse.json(result);
  } catch (error) {
    console.error("[api/books/:id/pages] failed:", error);
    return NextResponse.json(
      { error: "Unable to load pages right now." },
      { status: 502 }
    );
  }
}
