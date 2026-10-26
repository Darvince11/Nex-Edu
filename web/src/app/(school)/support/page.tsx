"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  Textarea,
} from "@/components/ui";
import { api, type Paged, type Student } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Goal = { goal: string; measure: string; status: "working" | "met" | "not_met" };
type Plan = {
  id: string;
  student: string;
  student_name: string;
  student_class: string;
  needs: string[];
  need_labels: string[];
  summary?: string;
  goals: Goal[];
  adjustments: string;
  extra_time_percent: number;
  review_on: string | null;
  shared_with_parents: boolean;
  status: string;
};
type Note = { id: string; date: string; text: string; written_by_name: string };

const NEEDS: [string, string][] = [
  ["learning", "Learning difficulty (e.g. dyslexia)"],
  ["hearing", "Hearing"],
  ["vision", "Sight"],
  ["physical", "Physical or mobility"],
  ["speech", "Speech and language"],
  ["emotional", "Social, emotional or behavioural"],
  ["attention", "Attention (e.g. ADHD)"],
  ["autism", "Autism"],
  ["gifted", "Gifted and talented"],
  ["other", "Other"],
];
const GOAL_LABEL = { working: "Working on it", met: "Met", not_met: "Not met yet" } as const;

/** Learning support plans: written by whoever runs support; teachers and parents see what they need. */
export default function SupportPage() {
  const { can } = useSchool();
  const manage = can(PERM.SUPPORT_MANAGE);
  const [open, setOpen] = useState<Plan | "new" | null>(null);
  const plans = useQuery({
    queryKey: ["support-plans"],
    queryFn: () => api.get<Plan[]>("/api/v1/support/plans"),
  });
  return (
    <>
      <PageHeader
        title="Learning support"
        description={
          manage
            ? "Plans for pupils with additional needs. Summaries and notes are confidential and every look is recorded."
            : "What to do for pupils with additional needs."
        }
        actions={manage && <Button onClick={() => setOpen("new")}>New plan</Button>}
      />
      <ErrorText error={plans.error} />
      {plans.isPending ? (
        <Loading />
      ) : plans.data?.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {plans.data.map((p) => (
            <Card
              key={p.id}
              title={`${p.student_name}${p.student_class ? ` (${p.student_class})` : ""}`}
              actions={
                manage && (
                  <Button
                    variant="ghost"
                    onClick={() => setOpen(p)}
                    aria-label={`Open plan for ${p.student_name}`}
                  >
                    Open
                  </Button>
                )
              }
            >
              <div className="mb-2 flex flex-wrap gap-1">
                {p.need_labels.map((n) => (
                  <Badge key={n} tone="blue">
                    {n}
                  </Badge>
                ))}
              </div>
              {p.adjustments && (
                <p className="text-sm">
                  <span className="font-medium">In class: </span>
                  {p.adjustments}
                </p>
              )}
              {p.extra_time_percent > 0 && (
                <p className="text-sm">{p.extra_time_percent}% extra time in tests.</p>
              )}
              {p.goals.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-sm">
                  {p.goals.map((g) => (
                    <li key={g.goal}>
                      {g.goal}{" "}
                      <span className="text-neutral-600 dark:text-neutral-400">
                        ({GOAL_LABEL[g.status] ?? g.status})
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {p.review_on && (
                <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
                  Review on {formatDate(p.review_on)}
                </p>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <Empty>No learning support plans.</Empty>
      )}
      <Modal
        open={open !== null}
        onClose={() => setOpen(null)}
        title={open === "new" ? "New learning support plan" : "Learning support plan"}
      >
        {open !== null && <PlanForm plan={open === "new" ? null : open} onDone={() => setOpen(null)} />}
      </Modal>
    </>
  );
}

function PlanForm({ plan, onDone }: { plan: Plan | null; onDone: () => void }) {
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [needs, setNeeds] = useState<string[]>(plan?.needs ?? []);
  const [goals, setGoals] = useState<Goal[]>(plan?.goals ?? []);
  const full = useQuery({
    queryKey: ["support-plan", plan?.id],
    queryFn: () => api.get<Plan>(`/api/v1/support/plans/${plan?.id}`),
    enabled: Boolean(plan),
  });
  const pupils = useQuery({
    queryKey: ["students", "support-search", q],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?page_size=20&q=${encodeURIComponent(q.trim())}`),
    enabled: !plan && q.trim().length >= 2,
  });
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      plan ? api.patch(`/api/v1/support/plans/${plan.id}`, body) : api.post("/api/v1/support/plans", body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["support-plans"] });
      onDone();
    },
  });
  if (plan && !full.data) return full.error ? <ErrorText error={full.error} /> : <Loading />;
  const p = full.data ?? plan;
  return (
    <div className="flex flex-col gap-5">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
          save.mutate({
            ...(plan ? {} : { student: f.student }),
            needs,
            summary: f.summary,
            goals: goals.filter((g) => g.goal.trim()),
            adjustments: f.adjustments,
            extra_time_percent: Number(f.extra || 0),
            review_on: f.review_on || null,
            shared_with_parents: f.shared === "on",
            status: f.status ?? "active",
          });
        }}
      >
        {!plan && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Find the pupil">
              <Input value={q} onChange={(e) => setQ(e.target.value)} />
            </Field>
            <Field label="Pupil">
              <Select name="student" required defaultValue="">
                <option value="" disabled>
                  {q.trim().length >= 2 ? "Choose" : "Search first"}
                </option>
                {pupils.data?.results.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.first_name} {s.last_name} {s.arm_name ? `(${s.arm_name})` : ""}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        )}
        <fieldset className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
          <legend className="px-1 text-sm font-medium">Areas of need</legend>
          <div className="grid gap-1 sm:grid-cols-2">
            {NEEDS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-brand"
                  checked={needs.includes(value)}
                  onChange={(e) =>
                    setNeeds((all) => (e.target.checked ? [...all, value] : all.filter((n) => n !== value)))
                  }
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Confidential summary" hint="Only people who run learning support can read this.">
          <Textarea name="summary" rows={3} maxLength={4000} defaultValue={p?.summary ?? ""} />
        </Field>
        <Field label="What every teacher should do" hint="Teachers of this pupil see this.">
          <Textarea name="adjustments" rows={2} maxLength={1000} defaultValue={p?.adjustments ?? ""} />
        </Field>
        <fieldset className="flex flex-col gap-2 rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
          <legend className="px-1 text-sm font-medium">Goals</legend>
          {goals.map((g, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: goals are edited in place; order is the identity.
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_9rem_auto] sm:items-end">
              <Field label="Goal">
                <Input
                  value={g.goal}
                  onChange={(e) =>
                    setGoals((all) => all.map((x, j) => (j === i ? { ...x, goal: e.target.value } : x)))
                  }
                />
              </Field>
              <Field label="How we'll know">
                <Input
                  value={g.measure}
                  onChange={(e) =>
                    setGoals((all) => all.map((x, j) => (j === i ? { ...x, measure: e.target.value } : x)))
                  }
                />
              </Field>
              <Field label="Progress">
                <Select
                  value={g.status}
                  onChange={(e) =>
                    setGoals((all) =>
                      all.map((x, j) => (j === i ? { ...x, status: e.target.value as Goal["status"] } : x)),
                    )
                  }
                >
                  <option value="working">Working on it</option>
                  <option value="met">Met</option>
                  <option value="not_met">Not met yet</option>
                </Select>
              </Field>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setGoals((all) => all.filter((_, j) => j !== i))}
                aria-label={`Remove goal ${i + 1}`}
              >
                Remove
              </Button>
            </div>
          ))}
          <div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setGoals((all) => [...all, { goal: "", measure: "", status: "working" }])}
            >
              Add a goal
            </Button>
          </div>
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Extra time in tests (%)">
            <Input name="extra" type="number" min={0} max={100} defaultValue={p?.extra_time_percent ?? 0} />
          </Field>
          <Field label="Review on (optional)">
            <Input name="review_on" type="date" defaultValue={p?.review_on ?? ""} />
          </Field>
          {plan && (
            <Field label="Plan">
              <Select name="status" defaultValue={p?.status ?? "active"}>
                <option value="active">Active</option>
                <option value="closed">Closed</option>
              </Select>
            </Field>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="shared"
            defaultChecked={p?.shared_with_parents ?? false}
            className="size-4 accent-brand"
          />{" "}
          Share the goals and adjustments with the parents
        </label>
        <ErrorText error={save.error} />
        <div className="flex justify-end">
          <Button type="submit" busy={save.isPending} disabled={!needs.length}>
            Save plan
          </Button>
        </div>
      </form>
      {plan && <Notes planId={plan.id} />}
    </div>
  );
}

function Notes({ planId }: { planId: string }) {
  const client = useQueryClient();
  const notes = useQuery({
    queryKey: ["support-notes", planId],
    queryFn: () => api.get<Note[]>(`/api/v1/support/plans/${planId}/notes`),
  });
  const add = useMutation({
    mutationFn: (text: string) => api.post(`/api/v1/support/plans/${planId}/add_note`, { text }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["support-notes", planId] }),
  });
  return (
    <section
      aria-labelledby="notes-title"
      className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <h3 id="notes-title" className="mb-1 font-medium">
        Progress notes (confidential)
      </h3>
      <Alert>Opening these notes is recorded in the audit log.</Alert>
      <ErrorText error={notes.error ?? add.error} />
      {notes.data?.length ? (
        <ul className="my-3 flex flex-col gap-2 text-sm">
          {notes.data.map((n) => (
            <li key={n.id}>
              <span className="text-xs text-neutral-600 dark:text-neutral-400">
                {formatDate(n.date)} · {n.written_by_name}
              </span>
              <p className="whitespace-pre-wrap">{n.text}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="my-3 text-sm text-neutral-600 dark:text-neutral-300">No notes yet.</p>
      )}
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          add.mutate(String(new FormData(form).get("text") ?? ""), { onSuccess: () => form.reset() });
        }}
      >
        <Field label="New note">
          <Textarea name="text" required rows={2} maxLength={4000} />
        </Field>
        <div className="flex justify-end">
          <Button type="submit" variant="secondary" busy={add.isPending}>
            Add note
          </Button>
        </div>
      </form>
    </section>
  );
}
