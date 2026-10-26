"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  Alert,
  Button,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import { api, type CalendarEntry, type CalendarKind } from "@/lib/api";
import { todayInAccra } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

const KINDS: Record<CalendarKind, { label: string; chip: string }> = {
  public_holiday: {
    label: "Public holiday",
    chip: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  },
  holiday: {
    label: "School holiday",
    chip: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  },
  term: {
    label: "Term dates",
    chip: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  },
  exam: { label: "Exams", chip: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200" },
  meeting: { label: "Meeting", chip: "bg-brand/10 text-brand-strong dark:bg-brand/25 dark:text-brand-sky" },
  event: {
    label: "School event",
    chip: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
  },
  other: {
    label: "Other",
    chip: "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
  },
};
const EDITABLE_KINDS = ["event", "meeting", "exam", "holiday", "other"] as const;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Dates as YYYY-MM-DD in UTC (Ghana keeps GMT all year). */
const iso = (d: Date) => d.toISOString().slice(0, 10);
const parse = (s: string) => new Date(`${s}T00:00:00Z`);
const addDays = (s: string, n: number) => {
  const d = parse(s);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
};
const fmt = (s: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: "UTC" }).format(parse(s));

/** The six weeks shown for the month containing `month` (YYYY-MM-01), Monday first. */
function gridFor(month: string): string[] {
  const first = parse(month);
  const offset = (first.getUTCDay() + 6) % 7;
  const start = addDays(month, -offset);
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

function onDay(entries: CalendarEntry[], day: string) {
  return entries.filter((e) => e.starts_on <= day && e.ends_on >= day);
}

function when(e: CalendarEntry): string {
  const days =
    e.ends_on === e.starts_on
      ? fmt(e.starts_on, { weekday: "short", day: "numeric", month: "short" })
      : `${fmt(e.starts_on, { day: "numeric", month: "short" })} – ${fmt(e.ends_on, { day: "numeric", month: "short" })}`;
  const time = e.starts_at
    ? ` · ${e.starts_at.slice(0, 5)}${e.ends_at ? `–${e.ends_at.slice(0, 5)}` : ""}`
    : "";
  return days + time;
}

/** Term dates, holidays, exams and meetings: everyone reads, school leaders add. */
export default function CalendarPage() {
  const { can } = useSchool();
  const manage = can(PERM.CALENDAR_MANAGE);
  const today = todayInAccra();
  const [month, setMonth] = useState(`${today.slice(0, 7)}-01`);
  const [editing, setEditing] = useState<CalendarEntry | "new" | null>(null);
  const days = gridFor(month);
  const first = days[0] ?? month;
  const last = days[days.length - 1] ?? month;
  const entries = useQuery({
    queryKey: ["calendar", first, last],
    queryFn: () => api.get<CalendarEntry[]>(`/api/v1/calendar?start=${first}&end=${last}`),
    placeholderData: keepPreviousData,
  });
  const shift = (n: number) => {
    const d = parse(month);
    d.setUTCMonth(d.getUTCMonth() + n);
    setMonth(iso(d));
  };
  const all = entries.data ?? [];
  const thisMonth = all.filter((e) => e.ends_on >= month && e.starts_on.slice(0, 7) <= month.slice(0, 7));
  const title = fmt(month, { month: "long", year: "numeric" });

  return (
    <>
      <PageHeader
        title="Calendar"
        description="Term dates, holidays, exams and school events."
        actions={manage && <Button onClick={() => setEditing("new")}>Add to calendar</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={() => shift(-1)} aria-label="Previous month">
          ‹
        </Button>
        <h2 className="min-w-40 text-center text-lg font-medium" aria-live="polite">
          {title}
        </h2>
        <Button variant="secondary" onClick={() => shift(1)} aria-label="Next month">
          ›
        </Button>
        <Button variant="ghost" onClick={() => setMonth(`${today.slice(0, 7)}-01`)}>
          Today
        </Button>
        <ul className="ml-auto flex flex-wrap gap-2 text-xs" aria-label="Key">
          {(["term", "public_holiday", "holiday", "exam", "meeting", "event"] as const).map((k) => (
            <li key={k} className={`rounded-full px-2 py-0.5 ${KINDS[k].chip}`}>
              {KINDS[k].label}
            </li>
          ))}
        </ul>
      </div>
      <ErrorText error={entries.error} />
      {entries.isPending ? (
        <Loading />
      ) : (
        <>
          <div
            className="hidden overflow-hidden rounded-card border border-neutral-200 sm:block dark:border-neutral-800"
            aria-hidden
          >
            <div className="grid grid-cols-7 border-b border-neutral-200 bg-neutral-50 text-xs font-medium text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
              {WEEKDAYS.map((d) => (
                <div key={d} className="px-2 py-1.5">
                  {d}
                </div>
              ))}
            </div>
            <div className="grid grid-cols-7">
              {days.map((day) => {
                const items = onDay(all, day);
                const inMonth = day.slice(0, 7) === month.slice(0, 7);
                return (
                  <div
                    key={day}
                    className={`min-h-24 border-b border-r border-neutral-100 p-1.5 dark:border-neutral-800 ${inMonth ? "bg-white dark:bg-neutral-950" : "bg-neutral-50 text-neutral-600 dark:bg-neutral-900 dark:text-neutral-400"}`}
                  >
                    <div
                      className={`mb-1 text-xs ${day === today ? "inline-flex size-6 items-center justify-center rounded-full bg-brand font-semibold text-white" : ""}`}
                    >
                      {Number(day.slice(8))}
                    </div>
                    <ul className="flex flex-col gap-0.5">
                      {items.slice(0, 3).map((e) => (
                        <li
                          key={`${e.source}-${e.id ?? e.title}`}
                          className={`truncate rounded px-1 text-[11px] ${KINDS[e.kind].chip}`}
                        >
                          {e.title}
                        </li>
                      ))}
                      {items.length > 3 && (
                        <li className="px-1 text-[11px] text-neutral-500">+{items.length - 3} more</li>
                      )}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>

          <section aria-labelledby="agenda" className="mt-6">
            <h2 id="agenda" className="mb-2 font-medium">
              In {fmt(month, { month: "long" })}
            </h2>
            {thisMonth.length ? (
              <ul className="divide-y divide-neutral-100 rounded-card border border-neutral-200 bg-white dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
                {thisMonth.map((e) => (
                  <li
                    key={`${e.source}-${e.id ?? `${e.title}-${e.starts_on}`}`}
                    className="flex items-start gap-3 px-4 py-3"
                  >
                    <span
                      className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs ${KINDS[e.kind].chip}`}
                    >
                      {KINDS[e.kind].label}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">
                        {e.title}
                        {e.audience === "staff" && (
                          <span className="ml-2 text-xs text-neutral-500">Staff only</span>
                        )}
                      </div>
                      <div className="text-sm text-neutral-600 dark:text-neutral-300">
                        {when(e)}
                        {e.location ? ` · ${e.location}` : ""}
                      </div>
                      {e.description && (
                        <p className="mt-1 whitespace-pre-wrap text-sm text-neutral-600 dark:text-neutral-400">
                          {e.description}
                        </p>
                      )}
                    </div>
                    {manage && e.editable && (
                      <Button variant="ghost" onClick={() => setEditing(e)} aria-label={`Change ${e.title}`}>
                        Change
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-neutral-500">Nothing on the calendar this month.</p>
            )}
            <p className="mt-3 text-xs text-neutral-500">
              Ghana's public holidays are added for you. Eid-ul-Fitr, Shaqq Day and Eid-ul-Adha move each year
              {manage ? ": add them as holidays once they're announced." : "."}
            </p>
          </section>
        </>
      )}
      <Modal
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "Add to the calendar" : "Change calendar entry"}
      >
        {editing !== null && (
          <EventForm
            entry={editing === "new" ? null : editing}
            defaultDay={month.slice(0, 7) === today.slice(0, 7) ? today : month}
            onDone={() => setEditing(null)}
          />
        )}
      </Modal>
    </>
  );
}

function EventForm({
  entry,
  defaultDay,
  onDone,
}: {
  entry: CalendarEntry | null;
  defaultDay: string;
  onDone: () => void;
}) {
  const client = useQueryClient();
  const done = () => {
    void client.invalidateQueries({ queryKey: ["calendar"] });
    onDone();
  };
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      entry
        ? api.patch(`/api/v1/calendar/events/${entry.id}`, body)
        : api.post("/api/v1/calendar/events", body),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/api/v1/calendar/events/${entry?.id}`),
    onSuccess: done,
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      title: f.title,
      kind: f.kind,
      starts_on: f.starts_on,
      ends_on: f.ends_on || f.starts_on,
      starts_at: f.starts_at || null,
      ends_at: f.ends_at || null,
      location: f.location,
      description: f.description,
      audience: f.audience,
      ...(entry ? {} : { notify: f.notify === "on" }),
    });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <Field label="What's happening">
          <Input name="title" required maxLength={120} defaultValue={entry?.title} />
        </Field>
      </div>
      <Field label="Kind">
        <Select name="kind" defaultValue={entry?.kind ?? "event"}>
          {EDITABLE_KINDS.map((k) => (
            <option key={k} value={k}>
              {KINDS[k].label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Who it's for">
        <Select name="audience" defaultValue={entry?.audience ?? "everyone"}>
          <option value="everyone">Everyone</option>
          <option value="staff">Staff only</option>
        </Select>
      </Field>
      <Field label="Starts">
        <Input type="date" name="starts_on" required defaultValue={entry?.starts_on ?? defaultDay} />
      </Field>
      <Field label="Ends (optional)" hint="Leave empty for a one-day event.">
        <Input
          type="date"
          name="ends_on"
          defaultValue={entry && entry.ends_on !== entry.starts_on ? entry.ends_on : ""}
        />
      </Field>
      <Field label="From (optional)">
        <Input type="time" name="starts_at" defaultValue={entry?.starts_at?.slice(0, 5) ?? ""} />
      </Field>
      <Field label="Until (optional)">
        <Input type="time" name="ends_at" defaultValue={entry?.ends_at?.slice(0, 5) ?? ""} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Where (optional)">
          <Input name="location" maxLength={120} defaultValue={entry?.location} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label="Details (optional)">
          <Textarea name="description" maxLength={1000} rows={3} defaultValue={entry?.description} />
        </Field>
      </div>
      {!entry && (
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" name="notify" className="size-4 accent-brand" />
          Tell everyone it's for in their inbox
        </label>
      )}
      <div className="sm:col-span-2">
        <ErrorText error={save.error ?? remove.error} />
      </div>
      {entry && (
        <div className="sm:col-span-2">
          <Alert tone="info">Changes show on everyone's calendar straight away.</Alert>
        </div>
      )}
      <div className="flex justify-between gap-2 sm:col-span-2">
        {entry ? (
          <Button type="button" variant="danger" busy={remove.isPending} onClick={() => remove.mutate()}>
            Delete
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" busy={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}
