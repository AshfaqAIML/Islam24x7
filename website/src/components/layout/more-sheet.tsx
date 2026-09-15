"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookMarked,
  BookOpenText,
  Compass,
  Download,
  HandHeart,
  Home,
  Library,
  ScrollText,
  Search,
  Sparkles,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { mainNav, buildProgress, routes } from "@/config/site";
import { brand } from "@/config/brand";
import { cn } from "@/lib/utils";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Logo } from "@/components/brand/logo";
import { StarLattice } from "@/components/decor/islamic-pattern";

const navIcons: Record<string, LucideIcon> = {
  Home,
  Search,
  Quran: BookOpenText,
  Hadith: ScrollText,
  Library: Library,
  "Ask AI": Sparkles,
};

export interface MoreSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * "More" sheet — the full navigation surface for mobile (opens from the
 * header hamburger and the bottom tab bar). Soon modules stay visible with
 * their phase, so the roadmap is honest and discoverable.
 */
export function MoreSheet({ open, onOpenChange }: MoreSheetProps) {
  const pathname = usePathname();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        className="flex max-h-[85svh] flex-col gap-0 rounded-t-2xl px-0 pb-[max(env(safe-area-inset-bottom),1rem)] pt-2"
      >
        <span
          aria-hidden="true"
          className="absolute left-1/2 top-2 h-1.5 w-12 -translate-x-1/2 rounded-full bg-muted-foreground/30"
        />
        <SheetHeader className="px-5 pb-2 pt-4 text-left">
          <div className="flex items-center gap-2.5">
            <Logo size={26} />
            <SheetTitle className="font-serif text-lg">Explore</SheetTitle>
          </div>
          <SheetDescription className="text-xs text-muted-foreground">
            Phase {buildProgress.currentPhase} of {buildProgress.totalPhases} —{" "}
            {buildProgress.phaseLabel}
          </SheetDescription>
        </SheetHeader>
        <Separator />

        <nav
          aria-label="All modules"
          className="scrollbar-elegant flex-1 overflow-y-auto px-3 py-3"
        >
          <ul className="space-y-1">
            {mainNav.map((item) => {
              const Icon = navIcons[item.label] ?? BookOpenText;
              const active = !item.soon && pathname === item.href;
              if (item.soon) {
                return (
                  <li key={item.label}>
                    <div
                      aria-disabled="true"
                      className="flex cursor-default items-center gap-3 rounded-xl px-3 py-2.5 text-muted-foreground/60"
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted/60">
                        <Icon className="h-4.5 w-4.5" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">{item.label}</span>
                        <span className="block text-xs text-muted-foreground/70">
                          Opens in Phase {item.phase}
                        </span>
                      </span>
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                        Soon
                      </span>
                    </div>
                  </li>
                );
              }
              return (
                <li key={item.label}>
                  <Link
                    href={item.href}
                    onClick={() => onOpenChange(false)}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "focus-ring flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors",
                      active
                        ? "bg-primary/10 text-primary"
                        : "text-foreground hover:bg-muted"
                    )}
                  >
                    <span
                      className={cn(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                        active
                          ? "bg-primary text-primary-foreground"
                          : "bg-secondary text-secondary-foreground"
                      )}
                    >
                      <Icon className="h-4.5 w-4.5" aria-hidden="true" />
                    </span>
                    <span className="text-sm font-medium">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>

          <Separator className="my-3" />

          <ul className="space-y-1">
            <li>
              <Link
                href={routes.download}
                onClick={() => onOpenChange(false)}
                className="focus-ring flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-gold/10"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gold/15">
                  <Download className="h-4.5 w-4.5 text-gold-foreground dark:text-gold" aria-hidden="true" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium">Get the Android app</span>
                  <span className="block text-xs text-muted-foreground">
                    APK · releases &amp; install steps
                  </span>
                </span>
              </Link>
            </li>
            <li className="flex items-center justify-between rounded-xl px-3 py-2.5">
              <span className="text-sm font-medium">Appearance</span>
              <ThemeToggle />
            </li>
          </ul>

          <div className="relative mt-4 overflow-hidden rounded-xl border bg-card/60 p-4 text-center">
            <StarLattice
              className="absolute inset-0 text-primary/[0.05]"
              aria-hidden="true"
            />
            <p className="relative font-serif text-sm text-muted-foreground">
              {brand.name} — {brand.tagline}
            </p>
            <p className="relative mt-1 text-[11px] text-muted-foreground/70">
              Every answer will cite its sources. Modules activate as the
              Knowledge Base connects.
            </p>
          </div>
        </nav>
      </SheetContent>
    </Sheet>
  );
}
