import { BookOpenText } from "lucide-react";
import { demoDailyAyah } from "@/lib/demo/content";
import { Card, CardContent } from "@/components/ui/card";
import { DemoBadge } from "@/components/common/states";

/**
 * Daily-ayah preview card. Shows a verbatim, universally-memorised verse,
 * clearly labeled as demo. When the Knowledge Base connects, this card is
 * fed by `GET /api/quran/daily` (service layer) — never invented content.
 */
export function DailyAyahCard() {
  const ayah = demoDailyAyah;

  return (
    <Card className="relative h-full overflow-hidden border-gold/25 bg-card">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-gold/60 via-gold/25 to-transparent"
      />
      <CardContent className="flex h-full flex-col gap-4 p-6">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <BookOpenText className="h-4 w-4 text-gold-foreground dark:text-gold" aria-hidden="true" />
            Daily ayah
          </div>
          <DemoBadge />
        </div>

        <p
          dir="rtl"
          lang="ar"
          className="mt-1 text-right font-arabic text-2xl leading-[2] text-foreground sm:text-[1.75rem]"
        >
          {ayah.arabic}
        </p>

        <p className="font-serif text-base italic leading-relaxed text-muted-foreground">
          “{ayah.translation}”
        </p>

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          <span className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">
            {ayah.citation}
          </span>
          <span className="text-[11px] leading-tight text-muted-foreground/80">
            Preview — daily verses will stream from the Knowledge Base
            <br aria-hidden="true" />
            (tap-to-open reader deep links arrive in Phase 6).
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
