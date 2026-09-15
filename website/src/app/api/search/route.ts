import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import type { SearchScope } from "@/types/knowledge-base";
import { search } from "@/services/search";

/**
 * GET /api/search?q=&scope=&limit=
 * Thin wrapper over the search service (the only KB consumer).
 */
const VALID_SCOPES: SearchScope[] = ["all", "quran", "hadith", "books", "dua"];

export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const q = (sp.get("q") ?? "").trim();
  const scopeParam = sp.get("scope") ?? "all";
  const limitParam = Number.parseInt(sp.get("limit") ?? "", 10);

  if (q.length < 2) {
    return NextResponse.json(
      { error: "Query must be at least 2 characters." },
      { status: 400 }
    );
  }
  if (!VALID_SCOPES.includes(scopeParam as SearchScope)) {
    return NextResponse.json(
      { error: `Invalid scope. Use one of: ${VALID_SCOPES.join(", ")}.` },
      { status: 400 }
    );
  }

  try {
    const result = await search({
      q,
      scope: scopeParam as SearchScope,
      limit: Number.isFinite(limitParam) ? limitParam : undefined,
    });
    return NextResponse.json(result);
  } catch (error) {
    console.error("[api/search] failed:", error);
    return NextResponse.json(
      { error: "Search failed unexpectedly." },
      { status: 500 }
    );
  }
}
