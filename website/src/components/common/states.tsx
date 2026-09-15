import { AlertTriangle, FlaskConical, Loader2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

/* ------------------------------- DemoBadge -------------------------------- */

/** Visible marker for clearly-labeled placeholder/demo data. */
export function DemoBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-gold/40 bg-gold/10 px-2 py-0.5 text-[11px] font-medium text-gold-foreground dark:text-gold",
        className
      )}
      title="Placeholder data for development — not real Islamic content"
    >
      <FlaskConical className="h-3 w-3" aria-hidden="true" />
      Demo
    </span>
  );
}

/* -------------------------------- SoonChip -------------------------------- */

export function SoonChip({ phase }: { phase?: number }) {
  return (
    <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
      Soon{phase ? ` · Phase ${phase}` : ""}
    </span>
  );
}

/* ------------------------------- EmptyState -------------------------------- */

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-card/50 px-6 py-12 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
        {Icon ? (
          <Icon className="h-5 w-5 text-secondary-foreground" aria-hidden="true" />
        ) : null}
      </div>
      <div className="space-y-1">
        <p className="font-serif font-semibold">{title}</p>
        {description ? (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

/* ------------------------------- ErrorState -------------------------------- */

export function ErrorState({
  title = "Something went wrong",
  description = "Please try again in a moment.",
  retryLabel = "Retry",
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  retryLabel?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-12 text-center",
        className
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
        <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden="true" />
      </div>
      <div className="space-y-1">
        <p className="font-serif font-semibold">{title}</p>
        <p className="mx-auto max-w-sm text-sm text-muted-foreground">
          {description}
        </p>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}

/* ------------------------------ LoadingState ------------------------------- */

export function LoadingState({
  variant = "cards",
  count = 3,
  className,
}: {
  variant?: "cards" | "list" | "text";
  count?: number;
  className?: string;
}) {
  if (variant === "text") {
    return (
      <div className={cn("space-y-2", className)} aria-busy="true">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    );
  }
  if (variant === "list") {
    return (
      <div className={cn("space-y-3", className)} aria-busy="true">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-2/5" />
              <Skeleton className="h-3 w-3/5" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div
      className={cn("grid gap-4 sm:grid-cols-2 lg:grid-cols-3", className)}
      aria-busy="true"
    >
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border bg-card p-4">
          <Skeleton className="mb-3 aspect-[3/4] w-24 rounded-lg" />
          <Skeleton className="mb-2 h-4 w-4/5" />
          <Skeleton className="h-3 w-2/5" />
        </div>
      ))}
      <span className="sr-only">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading
      </span>
    </div>
  );
}
