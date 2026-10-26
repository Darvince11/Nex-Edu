const cediFormatter = new Intl.NumberFormat("en-GH", {
  style: "currency",
  currency: "GHS",
  minimumFractionDigits: 2,
});

/** 125000 pesewas → "GH₵1,250.00". Amounts are always integer pesewas from the API. */
export function cedis(pesewas: number | null | undefined): string {
  return cediFormatter.format((pesewas ?? 0) / 100);
}

/** "1,250.50" or "1250.5" → 125050 pesewas. Returns null if not a valid amount. */
export function toPesewas(input: string): number | null {
  const cleaned = input.replace(/[,\s]|GH₵|GHS/gi, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, fraction = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "Africa/Accra",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return dateFormatter.format(new Date(value.length === 10 ? `${value}T12:00:00Z` : value));
}

const relative = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });

/** "3 hours ago", "yesterday", "2 weeks ago". Dashes when there's no date. */
export function timeAgo(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "—";
  const seconds = (new Date(value).getTime() - now.getTime()) / 1000;
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

/** Today's date in Ghana (GMT, no daylight saving) as YYYY-MM-DD. */
export function todayInAccra(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
