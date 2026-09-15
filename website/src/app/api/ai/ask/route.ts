import { NextResponse } from "next/server";
import { askLibrary, type AiScope } from "@/services/ai";

/**
 * POST /api/ai/ask — { question, scope, bookId?, chapterId? }
 *
 * The client never talks to the AI backend directly (no secrets client-side).
 * While the backend is unconfigured the route answers 503 with an explicit
 * `connected: false` payload — the UI renders the honest not-connected state.
 */
export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const { question, scope, bookId, chapterId } = (body ?? {}) as {
    question?: unknown;
    scope?: unknown;
    bookId?: unknown;
    chapterId?: unknown;
  };

  if (typeof question !== "string" || question.trim().length < 3) {
    return NextResponse.json(
      { error: "Provide a question of at least 3 characters." },
      { status: 400 }
    );
  }

  const result = await askLibrary({
    question: question.trim().slice(0, 2000),
    scope: (scope as AiScope) ?? "library",
    bookId: typeof bookId === "string" ? bookId : undefined,
    chapterId: typeof chapterId === "string" ? chapterId : undefined,
  });

  if (result.status === "unavailable") {
    return NextResponse.json(
      { connected: false, status: result.status, reason: result.reason },
      { status: 503 }
    );
  }

  return NextResponse.json({ connected: true, ...result });
}

/** GET /api/ai/ask — capability probe for the UI. */
export function GET() {
  const configured = Boolean(process.env.AI_API_URL);
  return NextResponse.json(
    {
      connected: configured,
      message: configured
        ? "AI backend configured."
        : "AI Knowledge Assistant is not connected yet. Set AI_API_URL to enable it.",
    },
    { status: configured ? 200 : 503 }
  );
}
