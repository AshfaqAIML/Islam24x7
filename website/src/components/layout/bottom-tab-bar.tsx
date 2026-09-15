"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenText, Home, Library, Menu, Search, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { tabNav } from "@/config/site";
import { cn } from "@/lib/utils";
import { MoreSheet } from "@/components/layout/more-sheet";

const tabIcons: Record<string, LucideIcon> = {
  home: Home,
  "book-open-text": BookOpenText,
  search: Search,
  library: Library,
  sparkles: Sparkles,
  menu: Menu,
};

/**
 * Mobile bottom tab bar (Phase 2) — fixed, thumb-reachable, frosted glass.
 * Five slots exactly; not-yet-shipped modules stay visible with a subtle
 * "Soon" state so the roadmap is honest. Hidden from `md` upwards.
 */
export function BottomTabBar() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <>
      <nav
        aria-label="Primary mobile navigation"
        className="fixed inset-x-0 bottom-0 z-50 border-t bg-background/85 backdrop-blur-lg supports-[backdrop-filter]:bg-background/70 md:hidden"
      >
        <ul className="mx-auto flex max-w-lg items-stretch px-2 pb-[max(env(safe-area-inset-bottom),0.25rem)] pt-1.5">
          {tabNav.map((tab) => {
            const Icon = tabIcons[tab.icon] ?? Home;

            if (tab.action === "more") {
              return (
                <li key={tab.key} className="flex-1">
                  <button
                    type="button"
                    onClick={() => setMoreOpen(true)}
                    aria-expanded={moreOpen}
                    aria-haspopup="dialog"
                    className="focus-ring flex w-full flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-muted-foreground transition-colors hover:text-foreground active:scale-95"
                  >
                    <span className="relative">
                      <Icon className="h-[22px] w-[22px]" aria-hidden="true" />
                    </span>
                    <span className="text-[11px] font-medium leading-none">
                      {tab.label}
                    </span>
                    <span aria-hidden="true" className="h-1 w-1 rounded-full bg-transparent" />
                  </button>
                </li>
              );
            }

            const active =
              tab.href != null &&
              (tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href));

            if (tab.soon) {
              return (
                <li key={tab.key} className="flex-1">
                  <span
                    aria-disabled="true"
                    aria-label={`${tab.label} — coming soon`}
                    className="flex w-full cursor-default flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-muted-foreground/50"
                  >
                    <span className="relative">
                      <Icon className="h-[22px] w-[22px]" aria-hidden="true" />
                      <span className="absolute -right-2.5 -top-1 rounded-full bg-muted px-1 text-[8px] font-bold uppercase leading-[1.3] text-muted-foreground">
                        Soon
                      </span>
                    </span>
                    <span className="text-[11px] font-medium leading-none">
                      {tab.label}
                    </span>
                    <span aria-hidden="true" className="h-1 w-1 rounded-full bg-transparent" />
                  </span>
                </li>
              );
            }

            return (
              <li key={tab.key} className="flex-1">
                <Link
                  href={tab.href ?? "/"}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "focus-ring relative flex w-full flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 transition-all active:scale-95",
                    active
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon className="h-[22px] w-[22px]" aria-hidden="true" />
                  <span className="text-[11px] font-medium leading-none">
                    {tab.label}
                  </span>
                  <span
                    aria-hidden="true"
                    className={cn(
                      "h-1 w-1 rounded-full bg-gold transition-opacity",
                      active ? "opacity-100" : "opacity-0"
                    )}
                  />
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <MoreSheet open={moreOpen} onOpenChange={setMoreOpen} />
    </>
  );
}
