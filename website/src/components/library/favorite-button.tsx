"use client";

import { Heart } from "lucide-react";
import { cn } from "@/lib/utils";
import { favoritesStore } from "@/lib/favorites-store";
import { useIsFavorite } from "@/hooks/use-favorites";
import { useToast } from "@/hooks/use-toast";

/**
 * Heart toggle for favorite books — persists locally (account sync in P8).
 * Rendered as a compact overlay button on cards and as a labelled action
 * on the book detail page.
 */
export function FavoriteButton({
  bookId,
  bookTitle,
  size = "sm",
  className,
}: {
  bookId: string;
  bookTitle?: string;
  size?: "sm" | "lg";
  className?: string;
}) {
  const isFavorite = useIsFavorite(bookId);
  const { toast } = useToast();

  const toggle = () => {
    const added = favoritesStore.toggle(bookId);
    toast({
      title: added ? "Added to favorites" : "Removed from favorites",
      description: bookTitle ?? undefined,
      duration: 1800,
    });
  };

  if (size === "lg") {
    return (
      <button
        type="button"
        onClick={toggle}
        aria-pressed={isFavorite}
        aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
        className={cn(
          "focus-ring inline-flex h-11 items-center gap-2 rounded-lg border px-4 text-sm font-medium transition-colors",
          isFavorite
            ? "border-destructive/40 bg-destructive/10 text-destructive"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
          className
        )}
      >
        <Heart
          className={cn(
            "h-4 w-4 transition-transform",
            isFavorite && "fill-current scale-110"
          )}
          aria-hidden="true"
        />
        {isFavorite ? "Favorited" : "Add to favorites"}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={isFavorite}
      aria-label={isFavorite ? "Remove from favorites" : "Add to favorites"}
      className={cn(
        "focus-ring flex h-9 w-9 shrink-0 items-center justify-center self-start rounded-full border transition-all active:scale-90",
        isFavorite
          ? "border-destructive/40 bg-destructive/10 text-destructive"
          : "border-border text-muted-foreground/70 hover:border-destructive/40 hover:text-destructive",
        className
      )}
    >
      <Heart
        className={cn(
          "h-4 w-4 transition-transform",
          isFavorite && "fill-current scale-110"
        )}
        aria-hidden="true"
      />
    </button>
  );
}
