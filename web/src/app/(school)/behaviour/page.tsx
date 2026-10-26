"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { BarList, ChartCard, SERIES_1 } from "@/components/charts";
import {
  Alert,
  Badge,
  Button,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { api, type Paged, type Student } from "@/lib/api";
import { formatDate, todayInAccra } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Action = {
  id: string;
  kind: string;
  kind_label: string;
  date: string;
  days: number | null;
  notes: string;
};
type Incident = {
  id: string;
  student: string;
  student_name: string;
  student_class: string;
  date: string;
  category: string;
  category_label: string;
  severity: string;
  severity_label: string;
  location: string;
  description: string;
  reported_by_name: string;
  status: "open" | "resolved";
  shared_with_parents_at: string | null;
  shared_summary: string;
  actions: Action[];
};
type Shared = {
  id: string;
  student_name: string;
  date: string;
  category_label: string;
  shared_summary: string;
  actions: { kind_label: string; date: string; days: number | null }[];
};
type Summary = {
  total: number;
  open: number;
  by_category: { category: string; label: string; count: number }[];
  repeat: { student: string; name: string; count: number }[];
};
type Note = { id: string; date: string; notes: string; follow_up_on: string | null; written_by_name: string };

const CATEGORIES: [string, string][] = [
  ["lateness", "Lateness"],
  ["disruption", "Disrupting lessons"],
  ["disrespect", "Disrespect or rudeness"],
  ["bullying", "Bullying"],
  ["fighting", "Fighting"],
  ["damage", "Damage to property"],
  ["dishonesty", "Dishonesty or cheating"],
  ["uniform", "Uniform or appearance"],
  ["truancy", "Leaving school without permission"],
  ["other", "Other"],
];
const ACTIONS: [string, string][] = [
  ["warning", "Warning"],
  ["detention", "Detention"],
  ["parents_met", "Met or called the parents"],
  ["duty", "Extra duty"],
  ["counselling", "Referred for counselling"],
  ["suspension", "Suspension"],
  ["other", "Other"],
];
const SEVERITY_TONE: Record<string, "grey" | "amber" | "red"> = {
  minor: "grey",
  moderate: "amber",
  serious: "red",
};

/** Behaviour: staff report and follow up incidents; parents see what's shared with them. */
export default function BehaviourPage() {
  const { can } = useSchool();
  if (!can(PERM.DISCIPLINE_RECORD, PERM.DISCIPLINE_MANAGE)) return <ForParents />;
  return <ForStaff />;
}

function ForParents() {
  const notes = useQuery({
    queryKey: ["incidents"],
    queryFn: () => api.get<Shared[]>("/api/v1/discipline/incidents"),
  });
  return (
    <>
      <PageHeader title="Behaviour" description="Notes the school has shared with you about your children." />
      <ErrorText error={notes.error} />
      {notes.isPending ? (
        <Loading />
      ) : notes.data?.length ? (
        <ul className="flex flex-col gap-3">
          {notes.data.map((n) => (
            <li
              key={n.id}
              className="rounded-card border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
            >
              <div className="text-sm text-neutral-600 dark:text-neutral-300">
                {n.student_name} · {formatDate(n.date)} · {n.category_label}
              </div>
              <p className="mt-1">{n.shared_summary}</p>
              {n.actions.length > 0 && (
                <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
                  {n.actions.map((a) => `${a.kind_label}${a.days ? ` (${a.days} days)` : ""}`).join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Nothing has been shared with you.</Empty>
      )}
    </>
  );
}

function ForStaff() {
  const { can } = useSchool();
  const manage = can(PERM.DISCIPLINE_MANAGE);
  const [status, setStatus] = useState("open");
  const [category, setCategory] = useState("");
  const [reporting, setReporting] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (category) params.set("category", category);
  const incidents = useQuery({
    queryKey: ["incidents", status, category],
    queryFn: () => api.get<Incident[]>(`/api/v1/discipline/incidents?${params}`),
    placeholderData: keepPreviousData,
  });
  const summary = useQuery({
    queryKey: ["incidents", "summary"],
    queryFn: () => api.get<Summary>("/api/v1/discipline/summary"),
    enabled: manage,
  });
  const chosen = incidents.data?.find((i) => i.id === open) ?? null;

  return (
    <>
      <PageHeader
        title="Behaviour"
        description={
          manage
            ? "Incidents across the school, what was done, and what parents were told."
            : "Report incidents and see those about your pupils."
        }
        actions={<Button onClick={() => setReporting(true)}>Report an incident</Button>}
      />
      {summary.data && (
        <div className="mb-5 grid gap-4 lg:grid-cols-3">
          <div className="grid gap-4">
            <Stat label="Incidents in the last 90 days" value={summary.data.total} />
            <Stat label="Still open" value={summary.data.open} />
          </div>
          <ChartCard
            title="By kind (90 days)"
            table={{
              head: ["Kind", "Incidents"],
              rows: summary.data.by_category.map((c) => [c.label, c.count]),
            }}
          >
            {summary.data.by_category.length ? (
              <BarList
                series={[{ name: "Incidents", color: SERIES_1 }]}
                format={(v) => String(v)}
                rows={summary.data.by_category.map((c) => ({ label: c.label, values: [c.count] }))}
              />
            ) : (
              <Empty>None.</Empty>
            )}
          </ChartCard>
          <section
            aria-labelledby="repeat-title"
            className="rounded-card border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
          >
            <h2 id="repeat-title" className="mb-2 font-medium">
              Pupils with 3 or more (90 days)
            </h2>
            {summary.data.repeat.length ? (
              <ul className="text-sm">
                {summary.data.repeat.map((r) => (
                  <li key={r.student} className="flex justify-between py-0.5">
                    {r.name} <span className="tabular-nums">{r.count}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-neutral-600 dark:text-neutral-300">None.</p>
            )}
          </section>
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-40">
          <Field label="Show">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="">All</option>
            </Select>
          </Field>
        </div>
        <div className="w-56">
          <Field label="Kind">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All kinds</option>
              {CATEGORIES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>
      <ErrorText error={incidents.error} />
      {incidents.isPending ? (
        <Loading />
      ) : incidents.data?.length ? (
        <Table head={["Date", "Pupil", "What", "Status", ""]}>
          {incidents.data.map((i) => (
            <tr key={i.id}>
              <Td className="whitespace-nowrap">{formatDate(i.date)}</Td>
              <Td>
                <span className="font-medium">{i.student_name}</span>
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                  {i.student_class}
                </span>
              </Td>
              <Td>
                {i.category_label}{" "}
                <Badge tone={SEVERITY_TONE[i.severity] ?? "grey"}>{i.severity_label}</Badge>
              </Td>
              <Td>
                {i.status === "open" ? "Open" : "Resolved"}
                {i.shared_with_parents_at && (
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">Parents told</span>
                )}
              </Td>
              <Td className="text-right">
                <Button
                  variant="ghost"
                  onClick={() => setOpen(i.id)}
                  aria-label={`Open incident for ${i.student_name} on ${formatDate(i.date)}`}
                >
                  Open
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No incidents to show.</Empty>
      )}
      <Modal open={reporting} onClose={() => setReporting(false)} title="Report an incident">
        {reporting && <ReportForm onDone={() => setReporting(false)} />}
      </Modal>
      <Modal open={chosen !== null} onClose={() => setOpen(null)} title="Incident">
        {chosen && <IncidentDetail incident={chosen} manage={manage} />}
      </Modal>
    </>
  );
}

function ReportForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const pupils = useQuery({
    queryKey: ["students", "behaviour-search", q],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?page_size=20&q=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2,
  });
  const save = useMutation({
    mutationFn: (body: Record<string, string>) => api.post("/api/v1/discipline/incidents", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["incidents"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    save.mutate(Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>);
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="Find the pupil">
        <Input value={q} onChange={(e) => setQ(e.target.value)} />
      </Field>
      <Field label="Pupil">
        <Select name="student" required defaultValue="">
          <option value="" disabled>
            {q.trim().length >= 2 ? "Choose" : "Search first"}
          </option>
          {pupils.data?.results.map((p) => (
            <option key={p.id} value={p.id}>
              {p.first_name} {p.last_name} {p.arm_name ? `(${p.arm_name})` : ""}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Date">
        <Input name="date" type="date" required defaultValue={todayInAccra()} max={todayInAccra()} />
      </Field>
      <Field label="Where (optional)">
        <Input name="location" maxLength={80} />
      </Field>
      <Field label="Kind">
        <Select name="category" required defaultValue="">
          <option value="" disabled>
            Choose
          </option>
          {CATEGORIES.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="How serious">
        <Select name="severity" defaultValue="minor">
          <option value="minor">Minor</option>
          <option value="moderate">Moderate</option>
          <option value="serious">Serious</option>
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Field label="What happened" hint="Staff only. Parents see a separate summary if a leader shares it.">
          <Textarea name="description" required maxLength={2000} rows={4} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Report
        </Button>
      </div>
    </form>
  );
}

function IncidentDetail({ incident, manage }: { incident: Incident; manage: boolean }) {
  const { can, hasModule } = useSchool();
  const client = useQueryClient();
  const refresh = () => void client.invalidateQueries({ queryKey: ["incidents"] });
  const [kind, setKind] = useState("warning");
  const [notesOpen, setNotesOpen] = useState(false);
  const act = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/discipline/incidents/${incident.id}/add_action`, body),
    onSuccess: refresh,
  });
  const share = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post(`/api/v1/discipline/incidents/${incident.id}/share`, body),
    onSuccess: refresh,
  });
  const toggle = useMutation({
    mutationFn: () =>
      api.post(
        `/api/v1/discipline/incidents/${incident.id}/${incident.status === "open" ? "resolve" : "reopen"}`,
      ),
    onSuccess: refresh,
  });
  return (
    <div className="flex flex-col gap-4 text-sm">
      <div>
        <div className="font-medium">
          {incident.student_name} ({incident.student_class}) · {incident.category_label} ·{" "}
          <Badge tone={SEVERITY_TONE[incident.severity] ?? "grey"}>{incident.severity_label}</Badge>
        </div>
        <div className="text-neutral-600 dark:text-neutral-300">
          {formatDate(incident.date)}
          {incident.location ? ` · ${incident.location}` : ""} · reported by {incident.reported_by_name}
        </div>
        <p className="mt-2 whitespace-pre-wrap">{incident.description}</p>
      </div>
      <section aria-labelledby="done-title">
        <h3 id="done-title" className="mb-1 font-medium">
          What was done
        </h3>
        {incident.actions.length ? (
          <ul className="list-disc pl-5">
            {incident.actions.map((a) => (
              <li key={a.id}>
                {a.kind_label}
                {a.days ? ` (${a.days} days)` : ""} · {formatDate(a.date)}
                {a.notes ? ` · ${a.notes}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-neutral-600 dark:text-neutral-300">Nothing yet.</p>
        )}
      </section>
      {manage && (
        <form
          className="grid gap-2 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
            act.mutate({ kind, date: f.date, days: f.days ? Number(f.days) : null, notes: f.notes });
          }}
        >
          <Field label="Action">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              {ACTIONS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="On">
            <Input name="date" type="date" required defaultValue={todayInAccra()} />
          </Field>
          {kind === "suspension" && (
            <Field label="Days">
              <Input name="days" type="number" min={1} max={30} required />
            </Field>
          )}
          <Field label="Note (optional, staff only)">
            <Input name="notes" maxLength={500} />
          </Field>
          <div className="flex items-end justify-end sm:col-span-2">
            <Button type="submit" variant="secondary" busy={act.isPending}>
              Record action
            </Button>
          </div>
        </form>
      )}
      {manage && (
        <section
          aria-labelledby="share-title"
          className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
        >
          <h3 id="share-title" className="mb-1 font-medium">
            Tell the parents
          </h3>
          {incident.shared_with_parents_at ? (
            <Alert tone="success">
              Told on {formatDate(incident.shared_with_parents_at)}: “{incident.shared_summary}”
            </Alert>
          ) : (
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                share.mutate({ summary: f.get("summary"), sms: f.get("sms") === "on" });
              }}
            >
              <Field label="What parents will read" hint="Written for parents; staff notes stay private.">
                <Textarea name="summary" required maxLength={500} rows={3} />
              </Field>
              {hasModule("sms") && (
                <label className="flex items-center gap-2">
                  <input type="checkbox" name="sms" className="size-4 accent-brand" /> Also by SMS
                </label>
              )}
              <div className="flex justify-end">
                <Button type="submit" variant="secondary" busy={share.isPending}>
                  Send to parents
                </Button>
              </div>
            </form>
          )}
        </section>
      )}
      <ErrorText error={act.error ?? share.error ?? toggle.error} />
      <div className="flex flex-wrap justify-between gap-2">
        {can(PERM.DISCIPLINE_COUNSEL) ? (
          <Button variant="ghost" onClick={() => setNotesOpen((v) => !v)}>
            {notesOpen ? "Hide counselling notes" : "Counselling notes"}
          </Button>
        ) : (
          <span />
        )}
        {manage && (
          <Button variant="secondary" busy={toggle.isPending} onClick={() => toggle.mutate()}>
            {incident.status === "open" ? "Mark resolved" : "Reopen"}
          </Button>
        )}
      </div>
      {notesOpen && <CounsellingNotes student={incident.student} />}
    </div>
  );
}

function CounsellingNotes({ student }: { student: string }) {
  const client = useQueryClient();
  const notes = useQuery({
    queryKey: ["counselling", student],
    queryFn: () => api.get<Note[]>(`/api/v1/discipline/counselling?student=${student}`),
  });
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/discipline/counselling", body),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["counselling", student] }),
  });
  return (
    <section
      aria-labelledby="notes-title"
      className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 id="notes-title" className="mb-1 font-medium">
        Counselling notes (confidential)
      </h3>
      <p className="mb-2 text-xs text-neutral-600 dark:text-neutral-400">
        Opening these is recorded in the audit log.
      </p>
      <ErrorText error={notes.error ?? add.error} />
      {notes.data?.length ? (
        <ul className="mb-3 flex flex-col gap-2">
          {notes.data.map((n) => (
            <li key={n.id}>
              <div className="text-xs text-neutral-600 dark:text-neutral-400">
                {formatDate(n.date)} · {n.written_by_name}
                {n.follow_up_on ? ` · follow up ${formatDate(n.follow_up_on)}` : ""}
              </div>
              <p className="whitespace-pre-wrap">{n.notes}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-3 text-neutral-600 dark:text-neutral-300">No notes yet.</p>
      )}
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
          add.mutate(
            { student, date: todayInAccra(), notes: f.notes, follow_up_on: f.follow_up_on || null },
            { onSuccess: () => form.reset() },
          );
        }}
      >
        <Field label="New note">
          <Textarea name="notes" required maxLength={4000} rows={3} />
        </Field>
        <Field label="Follow up on (optional)">
          <Input name="follow_up_on" type="date" />
        </Field>
        <div className="flex justify-end">
          <Button type="submit" variant="secondary" busy={add.isPending}>
            Save note
          </Button>
        </div>
      </form>
    </section>
  );
}
