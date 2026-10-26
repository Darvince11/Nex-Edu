"use client";

/**
 * Small, dependency-free charts for the dashboard. Specs follow the dataviz
 * method: thin marks (2px lines, bars <= 24px, 4px rounded data ends), 2px
 * surface gaps between touching marks, recessive hairline grid, a tooltip on
 * hover and keyboard focus, a legend for two or more series, and a table view
 * for every chart so no value depends on hovering or on colour.
 * Colours come from the --chart-* tokens in globals.css (validated light + dark).
 */

import {
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

export type Series = { name: string; color: string };
export const SERIES_1 = "var(--chart-1)";
export const SERIES_2 = "var(--chart-2)";

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(Math.floor(el.getBoundingClientRect().width));
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.floor(entry.contentRect.width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Round axis maximum and evenly spaced ticks (0 / 25 / 50 / 75 / 100, 0 / 2K / 4K …). */
export function niceTicks(max: number, count = 4): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const ticks: number[] = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(Number(v.toFixed(6)));
  const last = ticks.at(-1) ?? 0;
  if (last < max) ticks.push(last + step);
  return ticks;
}

export function compact(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(Math.round(value));
}

// --- Card with chart / table switch ---------------------------------------------------

export function ChartCard({
  title,
  description,
  table,
  legend,
  children,
  className = "",
}: {
  title: string;
  description?: ReactNode;
  table: { head: string[]; rows: ReactNode[][] };
  legend?: Series[];
  children: ReactNode;
  className?: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const heading = useId();
  return (
    <section
      aria-labelledby={heading}
      className={`flex min-w-0 flex-col rounded-card border border-neutral-200 bg-white p-4 shadow-card dark:border-neutral-800 dark:bg-neutral-900 ${className}`}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 id={heading} className="font-medium">
            {title}
          </h2>
          {description && <p className="mt-0.5 text-xs text-neutral-500">{description}</p>}
        </div>
        <fieldset className="flex shrink-0 rounded-control border border-neutral-200 p-0.5 text-xs dark:border-neutral-700">
          <legend className="sr-only">Show {title} as</legend>
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              type="button"
              aria-pressed={view === v}
              onClick={() => setView(v)}
              className={`rounded px-2 py-1 capitalize ${view === v ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100" : "text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"}`}
            >
              {v}
            </button>
          ))}
        </fieldset>
      </div>
      {legend && legend.length > 1 && view === "chart" && <Legend series={legend} />}
      {view === "chart" ? (
        <div className="min-w-0 flex-1">{children}</div>
      ) : (
        <div className="max-h-72 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs text-neutral-500 dark:bg-neutral-900">
              <tr>
                {table.head.map((h, i) => (
                  <th key={h} scope="col" className={`py-1.5 pr-3 font-medium ${i ? "text-right" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 dark:divide-neutral-800">
              {table.rows.map((row, r) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: rows are positional.
                <tr key={r}>
                  {row.map((cell, c) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: cells are positional.
                    <td key={c} className={`py-1.5 pr-3 ${c ? "text-right tabular-nums" : ""}`}>
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function Legend({ series }: { series: Series[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-600 dark:text-neutral-300">
      {series.map((s) => (
        <li key={s.name} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 rounded-sm" style={{ background: s.color }} />
          {s.name}
        </li>
      ))}
    </ul>
  );
}

/** Arrow keys step through the points; Home/End jump to the ends. */
function stepper(count: number, active: number | null, set: (i: number) => void) {
  return (e: KeyboardEvent) => {
    const keys: Record<string, number> = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 };
    if (e.key === "Home") set(0);
    else if (e.key === "End") set(count - 1);
    else if (e.key in keys) set(Math.max(0, Math.min(count - 1, (active ?? count - 1) + (keys[e.key] ?? 0))));
    else return;
    e.preventDefault();
  };
}

// --- Tooltip -----------------------------------------------------------------------------

type TipRow = { name: string; value: string; color?: string };

function Tooltip({
  x,
  y,
  width,
  title,
  rows,
}: {
  x: number;
  y: number;
  width: number;
  title: string;
  rows: TipRow[];
}) {
  const w = 176;
  const left = Math.max(0, Math.min(width - w, x - w / 2));
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-10 rounded-control border border-neutral-200 bg-white px-2.5 py-2 text-xs shadow-lg dark:border-neutral-700 dark:bg-neutral-800"
      style={{ left, top: Math.max(0, y), width: w }}
    >
      <div className="mb-1 text-neutral-500">{title}</div>
      <ul className="grid gap-0.5">
        {rows.map((row) => (
          <li key={row.name} className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5 text-neutral-600 dark:text-neutral-300">
              {row.color && (
                <span
                  aria-hidden="true"
                  className="h-0.5 w-3 shrink-0 rounded"
                  style={{ background: row.color }}
                />
              )}
              <span className="truncate">{row.name}</span>
            </span>
            <strong className="tabular-nums text-neutral-900 dark:text-neutral-50">{row.value}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- Trend (line + wash) -------------------------------------------------------------------

export type TrendPoint = { label: string; title: string; value: number | null; detail?: TipRow[] };

/** One series over time, with a crosshair that snaps to the nearest point. */
export function TrendChart({
  points,
  max,
  format,
  name,
  height = 200,
}: {
  points: TrendPoint[];
  max?: number;
  format: (v: number) => string;
  name: string;
  height?: number;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const gradient = useId();
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const ticks = niceTicks(max ?? Math.max(...values, 1));
  const top = ticks.at(-1) ?? 1;
  const pad = { left: 34, right: 44, top: 10, bottom: 24 };
  const plotW = Math.max(0, width - pad.left - pad.right);
  const plotH = height - pad.top - pad.bottom;
  const xAt = (i: number) => pad.left + (points.length > 1 ? (i * plotW) / (points.length - 1) : plotW / 2);
  const yAt = (v: number) => pad.top + plotH - (v / top) * plotH;

  const segments: string[] = [];
  let current = "";
  points.forEach((p, i) => {
    if (p.value === null) {
      if (current) segments.push(current);
      current = "";
      return;
    }
    current += `${current ? "L" : "M"}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`;
  });
  if (current) segments.push(current);
  const defined = points.map((p, i) => ({ ...p, i })).filter((p) => p.value !== null);
  const first = defined[0];
  const last = defined.at(-1);
  const area =
    first && last && defined.length > 1
      ? `M${xAt(first.i)},${yAt(0)}${defined.map((p) => `L${xAt(p.i).toFixed(1)},${yAt(p.value as number).toFixed(1)}`).join("")}L${xAt(last.i)},${yAt(0)}Z`
      : "";
  const labelEvery = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(plotW / 70))));

  const nearest = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (!rect || !points.length) return null;
    const x = clientX - rect.left - pad.left;
    const step = points.length > 1 ? plotW / (points.length - 1) : 1;
    return Math.max(0, Math.min(points.length - 1, Math.round(x / step)));
  };
  const point = active !== null ? points[active] : null;
  const shown = point ?? points.at(-1);

  return (
    // A slider: arrow keys move along the days and the value is read out.
    <div
      ref={box}
      role="slider"
      tabIndex={0}
      aria-label={name}
      aria-valuemin={0}
      aria-valuemax={Math.max(0, points.length - 1)}
      aria-valuenow={active ?? Math.max(0, points.length - 1)}
      aria-valuetext={
        shown ? `${shown.title}: ${shown.value === null ? "no register" : format(shown.value)}` : "No data"
      }
      onKeyDown={stepper(points.length, active, setActive)}
      onBlur={() => setActive(null)}
      className="relative rounded outline-none focus-visible:outline-2 focus-visible:outline-brand"
      style={{ height }}
    >
      {width > 0 && (
        <svg
          width={width}
          height={height}
          aria-hidden="true"
          className="touch-pan-y"
          onPointerMove={(e: PointerEvent) => setActive(nearest(e.clientX))}
          onPointerLeave={() => setActive(null)}
        >
          <defs>
            <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="var(--chart-1)" stopOpacity="0.16" />
              <stop offset="1" stopColor="var(--chart-1)" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={pad.left}
                x2={width - pad.right}
                y1={yAt(t)}
                y2={yAt(t)}
                stroke={t === 0 ? "var(--chart-axis)" : "var(--chart-grid)"}
                strokeWidth={1}
              />
              <text
                x={pad.left - 6}
                y={yAt(t)}
                dy="0.32em"
                textAnchor="end"
                className="fill-neutral-500 text-[10px] tabular-nums"
              >
                {format(t)}
              </text>
            </g>
          ))}
          {points.map((p, i) =>
            i % labelEvery === 0 || i === points.length - 1 ? (
              <text
                key={p.title}
                x={xAt(i)}
                y={height - 6}
                textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
                className="fill-neutral-500 text-[10px]"
              >
                {p.label}
              </text>
            ) : null,
          )}
          {area && <path d={area} fill={`url(#${gradient})`} />}
          {segments.map((d) => (
            <path
              key={d}
              d={d}
              fill="none"
              stroke="var(--chart-1)"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {last && (
            <>
              <circle
                cx={xAt(last.i)}
                cy={yAt(last.value as number)}
                r={4}
                fill="var(--chart-1)"
                stroke="var(--chart-surface)"
                strokeWidth={2}
              />
              <text
                x={xAt(last.i) + 8}
                y={yAt(last.value as number)}
                dy="0.32em"
                className="fill-neutral-800 text-[11px] font-medium tabular-nums dark:fill-neutral-100"
              >
                {format(last.value as number)}
              </text>
            </>
          )}
          {point && active !== null && (
            <g>
              <line
                x1={xAt(active)}
                x2={xAt(active)}
                y1={pad.top}
                y2={pad.top + plotH}
                stroke="var(--chart-axis)"
                strokeWidth={1}
              />
              {point.value !== null && (
                <circle
                  cx={xAt(active)}
                  cy={yAt(point.value)}
                  r={5}
                  fill="var(--chart-1)"
                  stroke="var(--chart-surface)"
                  strokeWidth={2}
                />
              )}
            </g>
          )}
        </svg>
      )}
      {point && active !== null && (
        <Tooltip
          x={xAt(active)}
          y={point.value !== null ? yAt(point.value) - 92 : pad.top}
          width={width}
          title={point.title}
          rows={[
            {
              name,
              value: point.value === null ? "No register" : format(point.value),
              color: "var(--chart-1)",
            },
            ...(point.detail ?? []),
          ]}
        />
      )}
    </div>
  );
}

// --- Horizontal bars (one or two stacked series) ---------------------------------------

export type BarRow = { label: string; values: number[] };

/** Category bars, longest-first if `sort`. Value at the bar tip; tooltip per row. */
export function BarList({
  rows,
  series,
  format,
  max,
}: {
  rows: BarRow[];
  series: Series[];
  format: (v: number) => string;
  max?: number;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<{ i: number; y: number } | null>(null);
  const top = max ?? Math.max(1, ...rows.map((r) => r.values.reduce((a, b) => a + b, 0)));
  const activeRow = active ? rows[active.i] : undefined;
  return (
    <div ref={box} className="relative">
      <ul className="grid gap-2">
        {rows.map((row, i) => {
          const total = row.values.reduce((a, b) => a + b, 0);
          const show = (e: { currentTarget: HTMLElement }) => {
            const parent = box.current?.getBoundingClientRect();
            const rect = e.currentTarget.getBoundingClientRect();
            setActive({ i, y: rect.top - (parent?.top ?? 0) - 8 });
          };
          return (
            <li
              key={row.label}
              // biome-ignore lint/a11y/noNoninteractiveTabindex: focus shows the same tooltip as hover.
              tabIndex={0}
              aria-label={`${row.label}: ${series.length > 1 ? row.values.map((v, s) => `${series[s]?.name ?? ""} ${format(v)}`).join(", ") : format(total)}`}
              onPointerEnter={show}
              onPointerLeave={() => setActive(null)}
              onFocus={show}
              onBlur={() => setActive(null)}
              className={`grid grid-cols-[minmax(4.5rem,7rem)_1fr] items-center gap-3 rounded py-0.5 outline-none focus-visible:outline-2 focus-visible:outline-brand ${active?.i === i ? "bg-neutral-50 dark:bg-neutral-800/60" : ""}`}
            >
              <span className="truncate text-xs text-neutral-600 dark:text-neutral-300">{row.label}</span>
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className="flex h-4 min-w-0 gap-[2px]"
                  style={{ width: `${(total / top) * 100}%` }}
                  aria-hidden="true"
                >
                  {row.values.map((v, s) =>
                    v > 0 ? (
                      <span
                        key={series[s]?.name ?? s}
                        className="h-full last:rounded-r-[4px]"
                        style={{ flexGrow: v, flexBasis: 0, background: series[s]?.color }}
                      />
                    ) : null,
                  )}
                </span>
                <span className="shrink-0 text-xs font-medium tabular-nums text-neutral-800 dark:text-neutral-100">
                  {format(total)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {activeRow && active && (
        <Tooltip
          x={width / 2 + 40}
          y={active.y - (series.length > 1 ? 70 : 52)}
          width={width}
          title={activeRow.label}
          rows={[
            ...activeRow.values.map((v, i) => ({
              name: series[i]?.name ?? "",
              value: format(v),
              color: series[i]?.color,
            })),
            ...(series.length > 1
              ? [{ name: "Total", value: format(activeRow.values.reduce((a, b) => a + b, 0)) }]
              : []),
          ]}
        />
      )}
    </div>
  );
}

// --- Columns (one series) ----------------------------------------------------------------

export type Column = { label: string; title: string; value: number };

export function ColumnChart({
  columns,
  format,
  name,
  height = 180,
}: {
  columns: Column[];
  format: (v: number) => string;
  name: string;
  height?: number;
}) {
  const [box, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const ticks = niceTicks(Math.max(1, ...columns.map((c) => c.value)), 3);
  const top = ticks.at(-1) ?? 1;
  const pad = { left: 34, bottom: 22, top: 8 };
  const plotW = Math.max(0, width - pad.left);
  const plotH = height - pad.bottom - pad.top;
  const band = columns.length ? plotW / columns.length : 0;
  const barW = Math.min(24, band * 0.6);
  const labelEvery = Math.max(1, Math.ceil(columns.length / Math.max(2, Math.floor(plotW / 56))));
  const yAt = (v: number) => pad.top + plotH - (v / top) * plotH;
  const cx = (i: number) => pad.left + band * i + band / 2;

  const shown = active !== null ? columns[active] : columns.at(-1);

  return (
    <div
      ref={box}
      role="slider"
      tabIndex={0}
      aria-label={name}
      aria-valuemin={0}
      aria-valuemax={Math.max(0, columns.length - 1)}
      aria-valuenow={active ?? Math.max(0, columns.length - 1)}
      aria-valuetext={shown ? `${shown.title}: ${format(shown.value)}` : "No data"}
      onKeyDown={stepper(columns.length, active, setActive)}
      onBlur={() => setActive(null)}
      className="relative rounded outline-none focus-visible:outline-2 focus-visible:outline-brand"
      style={{ height }}
    >
      {width > 0 && (
        <svg width={width} height={height} aria-hidden="true">
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={pad.left}
                x2={width}
                y1={yAt(t)}
                y2={yAt(t)}
                stroke={t === 0 ? "var(--chart-axis)" : "var(--chart-grid)"}
              />
              <text
                x={pad.left - 6}
                y={yAt(t)}
                dy="0.32em"
                textAnchor="end"
                className="fill-neutral-500 text-[10px] tabular-nums"
              >
                {format(t)}
              </text>
            </g>
          ))}
          {columns.map((c, i) => {
            const h = Math.max(c.value > 0 ? 2 : 0, yAt(0) - yAt(c.value));
            const x = cx(i) - barW / 2;
            const y = yAt(0) - h;
            const r = Math.min(4, barW / 2, h);
            return (
              <g key={c.title} onPointerEnter={() => setActive(i)} onPointerLeave={() => setActive(null)}>
                <rect x={cx(i) - band / 2} y={pad.top} width={band} height={plotH} fill="transparent" />
                {h > 0 && (
                  <path
                    d={`M${x},${yAt(0)}V${y + r}Q${x},${y} ${x + r},${y}H${x + barW - r}Q${x + barW},${y} ${x + barW},${y + r}V${yAt(0)}Z`}
                    fill="var(--chart-1)"
                    opacity={active === null || active === i ? 1 : 0.55}
                  />
                )}
                {(i % labelEvery === 0 || i === columns.length - 1) && (
                  <text x={cx(i)} y={height - 6} textAnchor="middle" className="fill-neutral-500 text-[10px]">
                    {c.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
      {active !== null && columns[active] && (
        <Tooltip
          x={cx(active)}
          y={yAt(columns[active].value) - 60}
          width={width}
          title={columns[active].title}
          rows={[{ name, value: format(columns[active].value), color: "var(--chart-1)" }]}
        />
      )}
    </div>
  );
}

// --- Meter -------------------------------------------------------------------------------

/** Part of a whole (fees collected of billed). The track is a light step of the same blue. */
export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div>
      {/* biome-ignore lint/a11y/useSemanticElements: <meter> can't be styled the same in every browser. */}
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        className="h-2.5 overflow-hidden rounded-full"
        style={{ background: "color-mix(in srgb, var(--chart-1) 16%, transparent)" }}
      >
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--chart-1)" }} />
      </div>
    </div>
  );
}
