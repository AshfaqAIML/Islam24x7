"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Smartphone } from "lucide-react";
import { brand } from "@/config/brand";
import { buildProgress, routes } from "@/config/site";
import { Button } from "@/components/ui/button";
import { StarLattice } from "@/components/decor/islamic-pattern";

/**
 * Phase-1 hero. Introduces the brand honestly: foundations are live,
 * knowledge modules arrive phase by phase. No fake content or features.
 */
export function Hero() {
  const reduceMotion = useReducedMotion();

  const fadeUp = (delay = 0) =>
    reduceMotion
      ? {}
      : {
          initial: { opacity: 0, y: 16 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.5, delay, ease: "easeOut" as const },
        };

  return (
    <section className="relative overflow-hidden border-b">
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-gradient-to-b from-primary/10 via-transparent to-transparent"
      />
      <StarLattice
        tile={72}
        className="absolute inset-0 h-full w-full text-gold opacity-[0.07]"
      />
      <div
        aria-hidden="true"
        className="absolute -top-24 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-gold/15 blur-3xl"
      />

      <div className="relative mx-auto max-w-6xl px-4 py-16 text-center sm:py-24">
        <motion.div {...fadeUp(0)}>
          <span className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-secondary/70 px-3 py-1 text-xs font-medium text-secondary-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-gold" aria-hidden="true" />
            Building · Phase {buildProgress.currentPhase} of{" "}
            {buildProgress.totalPhases}
          </span>
        </motion.div>

        <motion.h1
          {...fadeUp(0.08)}
          className="mx-auto mt-5 max-w-3xl font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl lg:text-6xl"
        >
          {brand.name}
        </motion.h1>

        <motion.p
          {...fadeUp(0.16)}
          className="mx-auto mt-3 max-w-xl text-base text-muted-foreground sm:text-lg"
        >
          {brand.tagline} — a calm, scholarly home for the Quran, Hadith,
          Islamic books and source-grounded AI research.
        </motion.p>

        <motion.div
          {...fadeUp(0.24)}
          className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <Button asChild size="lg" className="w-full sm:w-auto">
            <Link href={routes.download}>
              <Smartphone className="h-5 w-5" aria-hidden="true" />
              Get the Android App
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline" className="w-full sm:w-auto">
            <Link href="#modules">
              See what&apos;s inside
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
        </motion.div>

        <motion.p
          {...fadeUp(0.32)}
          className="mt-6 text-xs text-muted-foreground"
        >
          Built API-first on a dedicated Knowledge Base · every AI
          answer will cite its sources
        </motion.p>
      </div>
    </section>
  );
}
