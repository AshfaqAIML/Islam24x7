import Link from "next/link";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StarLattice } from "@/components/decor/islamic-pattern";

/** Branded 404 — every dead end stays calm and offers a way forward. */
export default function NotFound() {
  return (
    <main className="relative flex flex-1 items-center justify-center overflow-hidden">
      <StarLattice
        tile={72}
        className="absolute inset-0 h-full w-full text-primary opacity-[0.05]"
        aria-hidden="true"
      />
      <div className="relative mx-auto max-w-md px-4 py-20 text-center">
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-secondary">
          <Compass className="h-6 w-6 text-secondary-foreground" aria-hidden="true" />
        </span>
        <h1 className="mt-5 font-serif text-3xl font-semibold tracking-tight">
          This page isn&apos;t on the shelf
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The link may be outdated, or the volume hasn&apos;t arrived from the
          Knowledge Base yet.
        </p>
        <div className="mt-6 flex flex-col items-center justify-center gap-2.5 sm:flex-row">
          <Button asChild>
            <Link href="/">Back to home</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/library">Browse the library</Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
