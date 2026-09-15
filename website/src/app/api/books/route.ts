import { NextRequest, NextResponse } from "next/server";
import type { BookCategory, BookLanguage } from "@/types/knowledge-base";
import { listBooks, type BookSort } from "@/services/books";

/**
 * GET /api/books?q=&category=&language=&sort=&page=&pageSize=
 * Backed by the services layer (Knowledge Base proxy or labeled demo data).
 */
export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const page = Number(sp.get("page") ?? "1");
  const pageSize = Number(sp.get("pageSize") ?? "9");

  try {
    const result = await listBooks({
      q: sp.get("q") ?? undefined,
      category: (sp.get("category") as BookCategory | "all" | null) ?? undefined,
      language: (sp.get("language") as BookLanguage | "all" | null) ?? undefined,
      sort: (sp.get("sort") as BookSort | null) ?? undefined,
      page: Number.isFinite(page) ? page : 1,
      pageSize: Number.isFinite(pageSize) ? pageSize : undefined,
    });
    return NextResponse.json(result);
  } catch (error) {
    console.error("[api/books] failed:", error);
    return NextResponse.json(
      { error: "Unable to load books right now." },
      { status: 502 }
    );
  }
}
