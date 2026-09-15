import { cn } from "@/lib/utils";
import { brand } from "@/config/brand";

/**
 * Original brand mark: an eight-pointed geometric star (khatam) formed by
 * two overlapping squares — a classical motif rendered in a clean,
 * modern way. Gold outline, emerald core.
 */
export function BrandMark({
  className,
  size = 32,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      fill="none"
      aria-hidden="true"
      className={cn("shrink-0", className)}
    >
      {/* outer ring */}
      <circle
        cx="32"
        cy="32"
        r="29"
        className="stroke-gold/60"
        strokeWidth="1.5"
      />
      {/* eight-pointed star: two overlapping squares */}
      <rect
        x="16.5"
        y="16.5"
        width="31"
        height="31"
        rx="2"
        className="stroke-gold"
        strokeWidth="2.5"
      />
      <rect
        x="16.5"
        y="16.5"
        width="31"
        height="31"
        rx="2"
        transform="rotate(45 32 32)"
        className="stroke-gold"
        strokeWidth="2.5"
      />
      {/* core */}
      <circle cx="32" cy="32" r="5.5" className="fill-primary" />
    </svg>
  );
}

export function Logo({
  className,
  size = 32,
  withWordmark = true,
}: {
  className?: string;
  size?: number;
  withWordmark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark size={size} />
      {withWordmark && (
        <span className="whitespace-nowrap font-serif text-lg font-semibold leading-none tracking-tight">
          {brand.name}
        </span>
      )}
    </span>
  );
}
