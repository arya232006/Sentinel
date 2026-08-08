/**
 * The mark, drawn rather than described: one character per pixel on a 12x12
 * grid, `#` inked and `.` clear, so the glyph is legible in the source and can
 * be edited by typing the shape you want.
 *
 * A sun breaking a horizon: something watching from first light. It shares the
 * pixel idiom with the display face (Geist Pixel Grid), which is the reason it
 * is built on a grid at all rather than as curves.
 *
 * The glyph sits a half-cell high of centre on purpose — seven inked rows do
 * not centre on twelve, and the solid horizon bar carries enough weight that
 * splitting the difference downward would read as bottom-heavy.
 *
 * Lives outside components/landing because it is the site mark rather than a
 * landing-page component: the console wears it too, and it is a server
 * component here so importing it there costs no client bundle.
 */
const MARK = [
  "............",
  "............",
  "..#..##..#..",
  "............",
  "....####....",
  "#..######..#",
  "..########..",
  "............",
  ".##########.",
  "............",
  "............",
  "............",
];

/**
 * Size it at a multiple of 12px. The grid is 12 cells, so 12px puts one cell on
 * exactly one CSS pixel and two device pixels at 2x; at 16px a cell is 1.33px
 * and crispEdges has to round, landing some cells 2px wide and others 3px.
 */
export function Mark({ className = "" }: { className?: string }) {
  return (
    /* crispEdges because the whole point is square pixels — the default
       antialiasing would soften every edge into a grey fringe. */
    <svg
      viewBox="0 0 12 12"
      aria-hidden
      className={className}
      fill="currentColor"
      shapeRendering="crispEdges"
    >
      {MARK.flatMap((row, y) =>
        [...row].map((cell, x) =>
          cell === "#" ? (
            <rect key={`${x}-${y}`} x={x} y={y} width="1" height="1" />
          ) : null,
        ),
      )}
    </svg>
  );
}
