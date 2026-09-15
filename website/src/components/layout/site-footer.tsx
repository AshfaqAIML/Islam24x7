import Link from "next/link";
import { brand } from "@/config/brand";
import { routes } from "@/config/site";
import { featureFlags } from "@/config/site";
import { Logo } from "@/components/brand/logo";

/**
 * Sticky footer: sits at the bottom of short pages (mt-auto) and is pushed
 * down naturally when content exceeds the viewport.
 */
export function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="mt-auto border-t bg-secondary/40 pb-[env(safe-area-inset-bottom)]">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div>
            <Logo size={26} />
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              {brand.tagline} — an original Islamic knowledge platform built
              around a structured Knowledge Base and verifiable citations.
            </p>
          </div>
          <nav aria-label="Footer" className="flex items-center gap-4 text-sm">
            <Link
              href={routes.home}
              className="focus-ring rounded-md text-muted-foreground transition-colors hover:text-foreground"
            >
              Home
            </Link>
            <Link
              href={routes.download}
              className="focus-ring rounded-md text-muted-foreground transition-colors hover:text-foreground"
            >
              Android App
            </Link>
          </nav>
        </div>
        <div className="mt-6 flex flex-col gap-1 border-t pt-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>
            © {year} {brand.name}. All rights reserved.
          </p>
          <p>
            {featureFlags.useMockData
              ? "Development preview — sample data is clearly marked and no Islamic content is simulated."
              : "Development preview — modules arrive phase by phase."}
          </p>
        </div>
      </div>
    </footer>
  );
}
