"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Download, Menu, Search } from "lucide-react";
import { brand } from "@/config/brand";
import { mainNav, routes } from "@/config/site";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { MoreSheet } from "@/components/layout/more-sheet";

/**
 * Responsive site header. Mobile-first: logo + actions always visible,
 * full navigation from `md` up; hamburger opens the More sheet below `md`
 * (bottom tab bar covers the five primary slots).
 */
export function SiteHeader() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4">
        <Link
          href={routes.home}
          className="focus-ring rounded-md"
          aria-label={`${brand.name} — home`}
        >
          <Logo size={30} />
        </Link>

        {/* Desktop nav */}
        <TooltipProvider delayDuration={200}>
          <nav aria-label="Main navigation" className="hidden items-center gap-1 md:flex">
            {mainNav.map((item) => {
              if (item.soon) {
                return (
                  <Tooltip key={item.label}>
                    <TooltipTrigger asChild>
                      <span
                        aria-disabled="true"
                        className="flex cursor-default items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-2 text-sm text-muted-foreground/70"
                      >
                        {item.label}
                        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium leading-none text-muted-foreground">
                          Soon
                        </span>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      Planned for Phase {item.phase} — will activate once the
                      Knowledge Base is connected.
                    </TooltipContent>
                  </Tooltip>
                );
              }
              const active = pathname === item.href;
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "focus-ring whitespace-nowrap rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-secondary font-medium text-secondary-foreground"
                      : "text-foreground/80 hover:bg-muted hover:text-foreground"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </TooltipProvider>

        <div className="flex items-center gap-1.5">
          {/* Global search — one tap from the header on every screen size (§8) */}
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="text-foreground/80 hover:bg-muted hover:text-foreground"
            aria-label="Search Quran, Hadith and books"
          >
            <Link href={routes.search}>
              <Search className="h-5 w-5" aria-hidden="true" />
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            size="sm"
            className="hidden border-gold/50 text-gold-foreground hover:bg-gold/10 hover:text-gold-foreground dark:text-gold dark:hover:text-gold sm:inline-flex"
          >
            <Link href={routes.download}>
              <Download className="h-4 w-4" aria-hidden="true" />
              Get the App
            </Link>
          </Button>
          <Button
            asChild
            variant="outline"
            size="icon"
            className="border-gold/50 text-gold-foreground hover:bg-gold/10 dark:text-gold sm:hidden"
            aria-label="Download the Android app"
          >
            <Link href={routes.download}>
              <Download className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
          <ThemeToggle />
          {/* Mobile hamburger — opens the full More sheet */}
          <span className="md:hidden">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open menu"
              aria-haspopup="dialog"
              aria-expanded={moreOpen}
              onClick={() => setMoreOpen(true)}
            >
              <Menu className="h-5 w-5" />
            </Button>
          </span>
        </div>
      </div>
      <MoreSheet open={moreOpen} onOpenChange={setMoreOpen} />
    </header>
  );
}
