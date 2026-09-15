"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  BookOpenCheck,
  CircleHelp,
  Database,
  Keyboard,
  Lock,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type { Citation } from "@/types/knowledge-base";
import { aiScopes, type AiScope } from "@/services/ai";
import { brand } from "@/config/brand";
import { routes } from "@/config/site";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DemoBadge } from "@/components/common/states";
import { SourceCitation } from "@/components/citations/source-citation";
import { useToast } from "@/hooks/use-toast";

/**
 * §21–22 — AI foundation view.
 *
 * Integrity rules implemented here:
 *  - The Ask action is DISABLED until the backend connects; no simulated
 *    answers are ever produced.
 *  - The response interface (§22) is shown as a clearly-labeled DESIGN
 *    PREVIEW whose source cards are real, working deep links.
 */
export function AiView({
  connected,
  initialScope,
  initialBookId,
  initialBookTitle,
  initialChapterId,
}: {
  connected: boolean;
  initialScope?: AiScope;
  initialBookId?: string;
  initialBookTitle?: string | null;
  initialChapterId?: string;
}) {
  const { toast } = useToast();
  const [scope, setScope] = useState<AiScope>(
    initialBookId && !initialScope ? "book" : (initialScope ?? "library")
  );
  const [bookId, setBookId] = useState<string | undefined>(initialBookId);
  const [bookTitle, setBookTitle] = useState<string | undefined>(
    initialBookTitle ?? undefined
  );
  const [question, setQuestion] = useState("");

  /** Deep-linkable state without router churn (shareable /ai?scope=&book=). */
  const syncUrl = (next: { scope?: AiScope; book?: string | null }) => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (next.scope) params.set("scope", next.scope);
    if (next.book === null) params.delete("book");
    else if (next.book) params.set("book", next.book);
    const qs = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${qs ? `?${qs}` : ""}`);
  };

  const chooseScope = (next: AiScope) => {
    if ((next === "book" || next === "chapter") && !bookId) {
      toast({
        title: "Open a book first",
        description:
          "Use “Ask AI About This Book” on any book page — it opens the assistant with that book in scope.",
      });
      return;
    }
    setScope(next);
    syncUrl({ scope: next });
  };

  const clearBook = () => {
    setBookId(undefined);
    setBookTitle(undefined);
    setScope("library");
    syncUrl({ book: null, scope: "library" });
  };

  const canAsk = connected && question.trim().length >= 3;

  const submit = () => {
    if (!connected) {
      toast({
        title: "AI Knowledge Assistant is not connected yet",
        description:
          "Answers are never simulated. The assistant activates when the Knowledge Base AI backend is configured.",
      });
      return;
    }
    if (!canAsk) return;
    // Connected flow lands with the AI phase — the route /api/ai/ask already
    // proxies to the RAG service once AI_API_URL exists.
  };

  /** §22 preview citations — real, working deep links (not a fake answer). */
  const previewCitations = useMemo<Citation[]>(
    () => [
      {
        id: "preview-quran-1-1",
        source: { type: "quran", surah: 1, ayah: 1, surahName: "Al-Fātiḥah" },
        snippet:
          "In the name of Allah, the Most Gracious, the Most Merciful.",
      },
      {
        id: "preview-book-demo-tafsir-1",
        source: {
          type: "book",
          bookId: "demo-tafsir-1",
          bookTitle: "Sample Tafsir Volume (Demo)",
          chapterId: "demo-tafsir-1-ch-1",
          chapterTitle: "Chapter 1 — Introduction & Scope (Demo)",
          page: 1,
        },
      },
    ],
    []
  );

  return (
    <main className="mx-auto w-full max-w-4xl px-4 py-8 sm:py-10">
      {/* Scope selection */}
      <section aria-labelledby="ai-scope-heading">
        <h2 id="ai-scope-heading" className="text-sm font-semibold">
          Scope
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Choose what the assistant may search when answering.
        </p>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Answer scope">
          {aiScopes.map((s) => {
            const active = scope === s.id;
            const needsBook = (s.id === "book" || s.id === "chapter") && !bookId;
            return (
              <button
                key={s.id}
                type="button"
                aria-pressed={active}
                onClick={() => chooseScope(s.id)}
                className={cn(
                  "focus-ring rounded-full border px-3.5 py-2 text-sm transition-colors",
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "bg-card text-foreground/80 hover:border-primary/40 hover:bg-muted",
                  needsBook && !active && "text-muted-foreground/70"
                )}
              >
                {s.label}
                {needsBook ? <span className="ms-1.5 text-[10px]">via book page</span> : null}
              </button>
            );
          })}
        </div>

        {(scope === "book" || scope === "chapter") && bookId ? (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-gold/40 bg-gold/[0.06] px-3 py-2 text-sm">
            <BookOpenCheck className="h-4 w-4 shrink-0 text-gold-foreground dark:text-gold" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate">
              In scope: <span className="font-medium">{bookTitle ?? bookId}</span>
            </span>
            <button
              type="button"
              onClick={clearBook}
              aria-label="Clear book scope"
              className="focus-ring rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ) : null}
      </section>

      {/* Question composer */}
      <section aria-labelledby="ai-ask-heading" className="mt-8">
        <h2 id="ai-ask-heading" className="sr-only">
          Ask a question
        </h2>
        <div className="rounded-xl border bg-card shadow-sm">
          <label htmlFor="ai-question" className="sr-only">
            Your question
          </label>
          <textarea
            id="ai-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
            }}
            rows={4}
            maxLength={2000}
            placeholder="e.g. What do the sources say about patience in hardship?"
            className="w-full resize-none rounded-t-xl bg-transparent px-4 py-4 text-[15px] leading-relaxed outline-none placeholder:text-muted-foreground/60"
          />
          <div className="flex items-center justify-between gap-3 border-t px-4 py-3">
            <span className="hidden items-center gap-1.5 text-[11px] text-muted-foreground sm:flex">
              <Keyboard className="h-3.5 w-3.5" aria-hidden="true" />
              <kbd className="rounded border bg-muted px-1 font-sans text-[10px]">Ctrl</kbd>
              <span>+</span>
              <kbd className="rounded border bg-muted px-1 font-sans text-[10px]">Enter</kbd>
              <span>to ask</span>
            </span>
            <span className="text-[11px] text-muted-foreground sm:hidden">
              {question.length}/2000
            </span>
            <Button
              onClick={submit}
              disabled={!canAsk}
              className={cn(
                "gap-2 bg-gold text-gold-foreground hover:bg-gold/90 dark:text-gold-foreground dark:hover:bg-gold/90",
                !canAsk && "opacity-60"
              )}
            >
              {connected ? (
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Lock className="h-4 w-4" aria-hidden="true" />
              )}
              Ask
            </Button>
          </div>
        </div>
      </section>

      {/* Honest not-connected state (§21) */}
      {!connected ? (
        <section
          aria-live="polite"
          className="mt-6 rounded-xl border border-dashed border-gold/50 bg-gold/[0.05] p-5"
        >
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold/15">
              <AlertCircle className="h-4.5 w-4.5 text-gold-foreground dark:text-gold" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h3 className="font-semibold">
                AI Knowledge Assistant is not connected yet.
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                <span className="font-medium text-foreground">
                  Backend connection required.
                </span>{" "}
                The assistant activates once <code className="rounded bg-muted px-1 text-xs">AI_API_URL</code>{" "}
                points at the {brand.name} RAG service. Until then nothing is
                simulated — no generated answers, ever.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button asChild size="sm" variant="outline">
                  <Link href={routes.search}>
                    <Search className="h-4 w-4" aria-hidden="true" />
                    Search instead
                  </Link>
                </Button>
                <Button asChild size="sm" variant="ghost">
                  <Link href={routes.library}>
                    Browse the library
                    <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      {/* How answering will work */}
      <section aria-labelledby="ai-how-heading" className="mt-10">
        <h2 id="ai-how-heading" className="text-sm font-semibold">
          How answering will work
        </h2>
        <ol className="mt-3 grid gap-3 sm:grid-cols-3">
          {[
            {
              icon: CircleHelp,
              title: "1 · Ask",
              text: "Your question is sent to the Knowledge Base — never to a general-purpose chat model.",
            },
            {
              icon: Database,
              title: "2 · Retrieve",
              text: "The RAG pipeline retrieves the most relevant verified passages across the chosen scope.",
            },
            {
              icon: BookOpenCheck,
              title: "3 · Answer with sources",
              text: "Every claim links to its exact source: surah & ayah, collection & number, or book, chapter & page.",
            },
          ].map((step) => (
            <li key={step.title} className="rounded-xl border bg-card p-4">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary">
                  <step.icon className="h-3.5 w-3.5 text-secondary-foreground" aria-hidden="true" />
                </span>
                <p className="text-sm font-semibold">{step.title}</p>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {step.text}
              </p>
            </li>
          ))}
        </ol>
      </section>

      {/* §22 response interface — clearly-labeled design preview */}
      <section aria-labelledby="ai-preview-heading" className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="ai-preview-heading" className="text-sm font-semibold">
            Response interface
          </h2>
          <Badge variant="outline" className="gap-1 border-gold/50 text-[10px] uppercase tracking-wide text-gold-foreground dark:text-gold">
            Design preview — not a real answer
          </Badge>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          How every answer will be presented. The source cards below are fully
          functional — try “Open source”.
        </p>

        <div className="mt-4 overflow-hidden rounded-xl border">
          <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2.5">
            <Sparkles className="h-4 w-4 text-gold-foreground dark:text-gold" aria-hidden="true" />
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Answer
            </p>
            <span className="ms-auto">
              <DemoBadge />
            </span>
          </div>
          <div className="bg-card p-4">
            <p className="text-sm leading-relaxed text-muted-foreground">
              The assistant&apos;s grounded answer will appear here, written
              only from retrieved Knowledge Base passages. Sentences that draw
              on a source carry a reference marker; nothing outside the corpus
              is generated.
            </p>
          </div>
          <div className="border-t bg-muted/30 px-4 py-3">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Sources
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {previewCitations.map((citation) => (
                <SourceCitation key={citation.id} citation={citation} />
              ))}
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
