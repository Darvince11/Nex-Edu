"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
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

type Visit = {
  id: string;
  student: string;
  student_name: string;
  student_class?: string;
  arrived_at: string;
  left_at: string | null;
  complaint?: string;
  temperature?: string | null;
  treatment?: string;
  medication?: string;
  outcome?: string;
  outcome_label: string;
  seen_by_name?: string;
  parents_told_at?: string | null;
};
type Summary = {
  today: number;
  in_now: number;
  last_30_days: number;
  sent_home: number;
  frequent: { student: string; name: string; count: number }[];
};
type PupilHealth = { student: string; name: string; class: string; medical_notes: string; visits: Visit[] };

const OUTCOMES: [string, string][] = [
  ["returned", "Back to class"],
  ["rested", "Rested, then back to class"],
  ["sent_home", "Sent home"],
  ["collected", "Collected by a parent"],
  ["referred", "Referred to a clinic or hospital"],
];
const ALWAYS_TOLD = new Set(["sent_home", "collected", "referred"]);
const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

/** The sick bay: the nurse logs visits; class teachers and parents see their own pupils' visits. */
export default function SickBayPage() {
  const { can } = useSchool();
  return can(PERM.CLINIC_RECORD) ? <NurseDesk /> : <OwnVisits />;
}

function OwnVisits() {
  const { roles } = useSchool();
  const visits = useQuery({
    queryKey: ["clinic-visits", "own"],
    queryFn: () => api.get<Visit[]>("/api/v1/clinic/visits"),
  });
  const parent = roles.includes("parent");
  return (
    <>
      <PageHeader
        title="Sick bay"
        description={
          parent
            ? "Your children's visits to the school sick bay."
            : "When pupils in your class were in the sick bay."
        }
      />
      <ErrorText error={visits.error} />
      {visits.isPending ? (
        <Loading />
      ) : visits.data?.length ? (
        <Table
          head={
            parent
              ? ["When", "Child", "What was wrong", "What was done", "Outcome"]
              : ["When", "Pupil", "Outcome"]
          }
        >
          {visits.data.map((v) => (
            <tr key={v.id}>
              <Td className="whitespace-nowrap">
                {formatDate(v.arrived_at)}, {time(v.arrived_at)}
              </Td>
              <Td className="font-medium">{v.student_name}</Td>
              {parent && <Td>{v.complaint}</Td>}
              {parent && <Td>{[v.treatment, v.medication].filter(Boolean).join(" · ") || "—"}</Td>}
              <Td>{v.outcome_label || "In the sick bay"}</Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No sick bay visits.</Empty>
      )}
    </>
  );
}

function NurseDesk() {
  const [adding, setAdding] = useState(false);
  const [finishing, setFinishing] = useState<Visit | null>(null);
  const [day, setDay] = useState(todayInAccra());
  const summary = useQuery({
    queryKey: ["clinic-summary"],
    queryFn: () => api.get<Summary>("/api/v1/clinic/summary"),
  });
  const now = useQuery({
    queryKey: ["clinic-visits", "now"],
    queryFn: () => api.get<Visit[]>("/api/v1/clinic/visits?now=1"),
  });
  const onDay = useQuery({
    queryKey: ["clinic-visits", "day", day],
    queryFn: () => api.get<Visit[]>(`/api/v1/clinic/visits?date=${day}`),
    placeholderData: keepPreviousData,
  });
  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Sick bay"
        description="Log who comes in, what was done, and how it ended. Parents are told when a child goes home."
        actions={<Button onClick={() => setAdding(true)}>New visit</Button>}
      />
      {s && (
        <div className="mb-5 grid gap-4 sm:grid-cols-4">
          <Stat label="In the sick bay now" value={s.in_now} />
          <Stat label="Seen today" value={s.today} />
          <Stat label="Last 30 days" value={s.last_30_days} />
          <Stat label="Sent home (30 days)" value={s.sent_home} />
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="In the sick bay now">
            <ErrorText error={now.error} />
            {now.data?.length ? (
              <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
                {now.data.map((v) => (
                  <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <span>
                      <span className="font-medium">{v.student_name}</span> ({v.student_class}) since{" "}
                      {time(v.arrived_at)}
                      <span className="block text-neutral-600 dark:text-neutral-300">
                        {v.complaint}
                        {v.temperature ? ` · ${v.temperature}°C` : ""}
                      </span>
                    </span>
                    <Button variant="secondary" onClick={() => setFinishing(v)}>
                      Finish visit
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-neutral-600 dark:text-neutral-300">Nobody is in the sick bay.</p>
            )}
          </Card>
        </div>
        <Card title="Frequent visitors (30 days)">
          {s?.frequent.length ? (
            <ul className="text-sm">
              {s.frequent.map((f) => (
                <li key={f.student} className="flex justify-between py-0.5">
                  {f.name} <span className="tabular-nums">{f.count}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600 dark:text-neutral-300">None.</p>
          )}
        </Card>
      </div>
      <section aria-labelledby="day-title" className="mt-6">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-3">
          <h2 id="day-title" className="font-medium">
            Visits on {formatDate(day)}
          </h2>
          <div className="w-44">
            <Field label="Day">
              <Input
                type="date"
                value={day}
                max={todayInAccra()}
                onChange={(e) => setDay(e.target.value || todayInAccra())}
              />
            </Field>
          </div>
        </div>
        {onDay.data?.length ? (
          <Table head={["Time", "Pupil", "Complaint", "Done", "Outcome"]}>
            {onDay.data.map((v) => (
              <tr key={v.id}>
                <Td className="whitespace-nowrap tabular-nums">{time(v.arrived_at)}</Td>
                <Td>
                  <span className="font-medium">{v.student_name}</span>
                  <span className="block text-xs text-neutral-600 dark:text-neutral-400">
                    {v.student_class}
                  </span>
                </Td>
                <Td>
                  {v.complaint}
                  {v.temperature ? ` · ${v.temperature}°C` : ""}
                </Td>
                <Td>{[v.treatment, v.medication].filter(Boolean).join(" · ") || "—"}</Td>
                <Td>
                  {v.outcome_label || <Badge tone="amber">Still in</Badge>}
                  {v.parents_told_at && (
                    <span className="block text-xs text-neutral-600 dark:text-neutral-400">Parents told</span>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No visits that day.</Empty>
        )}
      </section>
      <Modal open={adding} onClose={() => setAdding(false)} title="New sick bay visit">
        {adding && <NewVisit onDone={() => setAdding(false)} />}
      </Modal>
      <Modal open={finishing !== null} onClose={() => setFinishing(null)} title="Finish visit">
        {finishing && <Finish visit={finishing} onDone={() => setFinishing(null)} />}
      </Modal>
    </>
  );
}

function useRefresh() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: ["clinic-visits"] });
    void client.invalidateQueries({ queryKey: ["clinic-summary"] });
  };
}

function OutcomeFields({
  outcome,
  setOutcome,
  allowStay,
}: {
  outcome: string;
  setOutcome: (v: string) => void;
  allowStay: boolean;
}) {
  const { hasModule } = useSchool();
  return (
    <>
      <Field label="How did it end?">
        <Select value={outcome} onChange={(e) => setOutcome(e.target.value)} required={!allowStay}>
          {allowStay ? (
            <option value="">Still in the sick bay</option>
          ) : (
            <option value="" disabled>
              Choose
            </option>
          )}
          {OUTCOMES.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </Select>
      </Field>
      {ALWAYS_TOLD.has(outcome) ? (
        <Alert>The parents will be told in their inbox.</Alert>
      ) : (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="tell_parents" className="size-4 accent-brand" /> Tell the parents
        </label>
      )}
      {hasModule("sms") && (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="sms" className="size-4 accent-brand" /> Also by SMS
        </label>
      )}
    </>
  );
}

function NewVisit({ onDone }: { onDone: () => void }) {
  const refresh = useRefresh();
  const [q, setQ] = useState("");
  const [student, setStudent] = useState("");
  const [outcome, setOutcome] = useState("");
  const pupils = useQuery({
    queryKey: ["students", "clinic-search", q],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?page_size=20&q=${encodeURIComponent(q.trim())}`),
    enabled: q.trim().length >= 2,
  });
  const health = useQuery({
    queryKey: ["clinic-pupil", student],
    queryFn: () => api.get<PupilHealth>(`/api/v1/clinic/pupils/${student}`),
    enabled: Boolean(student),
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/api/v1/clinic/visits", body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    save.mutate({
      student,
      complaint: f.complaint,
      temperature: f.temperature || null,
      treatment: f.treatment,
      medication: f.medication,
      outcome,
      tell_parents: f.tell_parents === "on",
      sms: f.sms === "on",
    });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Find the pupil">
          <Input value={q} onChange={(e) => setQ(e.target.value)} />
        </Field>
        <Field label="Pupil">
          <Select value={student} onChange={(e) => setStudent(e.target.value)} required>
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
      </div>
      {health.data && (
        <Alert tone={health.data.medical_notes ? "warning" : "info"}>
          {health.data.medical_notes
            ? `Medical notes: ${health.data.medical_notes}`
            : "No medical notes on file."}
          {health.data.visits.length > 0 && ` Last visit ${formatDate(health.data.visits[0]?.arrived_at)}.`}
        </Alert>
      )}
      <Field label="What's wrong">
        <Input name="complaint" required maxLength={500} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Temperature °C (optional)">
          <Input name="temperature" inputMode="decimal" placeholder="37.0" />
        </Field>
        <Field label="Medicine given (optional)" hint="Name and amount.">
          <Input name="medication" maxLength={300} />
        </Field>
      </div>
      <Field label="What was done (optional)">
        <Textarea name="treatment" maxLength={1000} rows={2} />
      </Field>
      <OutcomeFields outcome={outcome} setOutcome={setOutcome} allowStay />
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending} disabled={!student}>
          Save visit
        </Button>
      </div>
    </form>
  );
}

function Finish({ visit, onDone }: { visit: Visit; onDone: () => void }) {
  const refresh = useRefresh();
  const [outcome, setOutcome] = useState("");
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/api/v1/clinic/visits/${visit.id}`, body),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          outcome,
          treatment: f.treatment,
          medication: f.medication,
          tell_parents: f.tell_parents === "on",
          sms: f.sms === "on",
        });
      }}
    >
      <p className="text-sm">
        <span className="font-medium">{visit.student_name}</span> · {visit.complaint}
      </p>
      <Field label="What was done">
        <Textarea name="treatment" maxLength={1000} rows={2} defaultValue={visit.treatment} />
      </Field>
      <Field label="Medicine given (optional)">
        <Input name="medication" maxLength={300} defaultValue={visit.medication} />
      </Field>
      <OutcomeFields outcome={outcome} setOutcome={setOutcome} allowStay={false} />
      <ErrorText error={save.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={save.isPending}>
          Finish visit
        </Button>
      </div>
    </form>
  );
}
