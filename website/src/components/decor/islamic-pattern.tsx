import { cn } from "@/lib/utils";
import type { ComponentProps } from "react";

/**
 * Subtle Islamic geometric lattice — the classical "breath of the
 * compassionate" eight-pointed star tile.
 *
 * Implementation note (hydration-safety): this used to be an inline <svg>
 * whose <pattern> id came from useId(). In React 19 + Turbopack the
 * server/client ids diverged, causing a hydration attribute mismatch on
 * every page that renders the pattern. The tile is now a CSS mask over a
 * constant data-URI — no SVG ids, no randomness, identical server and
 * client markup, and the pattern even paints before hydration.
 *
 * Color: the element paints with `bg-current`, so parents style it exactly
 * as before with text-* + opacity-* utilities.
 *
 * Usage:
 *   <div className="relative">
 *     <StarLattice className="absolute inset-0 h-full w-full text-gold opacity-[0.07]" />
 *     ...content
 *   </div>
 */
const STAR_TILE_SVG =
  `<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 40 40'>` +
  `<g fill='none' stroke='#000' stroke-width='1'>` +
  `<rect x='10' y='10' width='20' height='20'/>` +
  `<rect x='10' y='10' width='20' height='20' transform='rotate(45 20 20)'/>` +
  `</g>` +
  `<g fill='#000'>` +
  `<circle cx='0' cy='0' r='1.2'/>` +
  `<circle cx='40' cy='0' r='1.2'/>` +
  `<circle cx='0' cy='40' r='1.2'/>` +
  `<circle cx='40' cy='40' r='1.2'/>` +
  `<circle cx='20' cy='20' r='1.4'/>` +
  `</g>` +
  `</svg>`;

const STAR_TILE_MASK = `url("data:image/svg+xml,${encodeURIComponent(STAR_TILE_SVG)}")`;

export function StarLattice({
  className,
  tile = 76,
  ...rest
}: ComponentProps<"div"> & { tile?: number }) {
  return (
    <div
      aria-hidden="true"
      className={cn("pointer-events-none select-none bg-current", className)}
      {...rest}
      style={{
        maskImage: STAR_TILE_MASK,
        WebkitMaskImage: STAR_TILE_MASK,
        maskSize: `${tile}px ${tile}px`,
        WebkitMaskSize: `${tile}px ${tile}px`,
        maskRepeat: "repeat",
        WebkitMaskRepeat: "repeat",
      }}
    />
  );
}
