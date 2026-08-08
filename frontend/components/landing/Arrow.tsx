/**
 * The chevron is set in Geist Pixel Grid, which draws glyphs as 30-unit squares
 * on a 38-unit pitch in a 1000-unit em. 1000/38 ≈ 26.32px is therefore the one
 * font size where a square lands on exactly one CSS pixel — at the 9px this used
 * to be, each square was under half a pixel and the grid would have smeared into
 * a grey smudge rather than reading as pixels at all.
 *
 * The glyph inks only 41% of its em box, so 26.32px still renders about 11px
 * tall. It also sits low: at line-height 1 the ink centre falls ~1.8px below the
 * line box centre, hence the lift on the inner span to re-centre it in the chip.
 *
 * Its own module rather than living in Hero.tsx, because Sections.tsx renders on
 * the server and importing this from a "use client" module would drag that whole
 * module — clock, hero image and all — across the boundary for a chevron.
 */
export function Arrow({
  // The default chip is a white veil, which is invisible on a light ground —
  // callers on the pale bands pass a dark one instead. The glyph itself is
  // always currentColor and needs no say in it.
  className = "bg-white/25 group-hover:bg-white/40",
}: {
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full transition ${className}`}
    >
      <span className="-translate-y-[1.8px] font-display text-[26.32px] leading-none">
        ›
      </span>
    </span>
  );
}
