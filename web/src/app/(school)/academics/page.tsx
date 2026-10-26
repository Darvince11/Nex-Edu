"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  PageHeader,
  Select,
  Table,
  Td,
} from "@/components/ui";
import { JoinLink } from "@/components/video-link";
import {
  type Assignment,
  api,
  type Level,
  type Member,
  type Period,
  type Session,
  type Term,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useArms, useCurrentTerm, useSchool, useSubjects, useTerms } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

const DAYS = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
type Tab = "year" | "classes" | "teachers" | "timetable";

export default function AcademicsPage() {
  const { can } = useSchool();
  const leader = can(PERM.ACADEMICS_MANAGE);
  const [tab, setTab] = useState<Tab>(leader ? "year" : "timetable");
  const tabs: [Tab, string][] = leader
    ? [
        ["year", "Academic year"],
        ["classes", "Classes & subjects"],
        ["teachers", "Teacher assignments"],
        ["timetable", "Timetable"],
      ]
    : [["timetable", "My timetable"]];
  return (
    <>
      <PageHeader title="Classes & timetable" />
      <div className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === key ? "border-brand font-medium" : "border-transparent text-neutral-500"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "year" && <YearSetup />}
      {tab === "classes" && <ClassesSetup />}
      {tab === "teachers" && <TeacherAssignments />}
      {tab === "timetable" && <Timetable leader={leader} />}
    </>
  );
}

function YearSetup() {
  const client = useQueryClient();
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () => api.get<Session[]>("/api/v1/academics/sessions"),
  });
  const terms = useTerms();
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["sessions"] });
    client.invalidateQueries({ queryKey: ["terms"] });
  };
  const addSession = useMutation({
    mutationFn: (b: unknown) => api.post("/api/v1/academics/sessions", b),
    onSuccess: refresh,
  });
  const addTerm = useMutation({
    mutationFn: (b: unknown) => api.post("/api/v1/academics/terms", b),
    onSuccess: refresh,
  });
  const makeCurrent = useMutation({
    mutationFn: (id: number) => api.post(`/api/v1/academics/terms/${id}/set_current`),
    onSuccess: refresh,
  });

  const form = (e: FormEvent<HTMLFormElement>) => Object.fromEntries(new FormData(e.currentTarget));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Academic years">
        <ul className="mb-3 text-sm">
          {sessions.data?.map((s) => (
            <li key={s.id} className="py-0.5">
              {s.name} · {formatDate(s.starts_on)} – {formatDate(s.ends_on)}{" "}
              {s.is_current && <Badge tone="green">current</Badge>}
            </li>
          ))}
        </ul>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            addSession.mutate(form(e));
          }}
          className="grid gap-2 sm:grid-cols-3 sm:items-end"
        >
          <Field label="Name">
            <Input name="name" placeholder="2026/2027" required />
          </Field>
          <Field label="Starts">
            <Input name="starts_on" type="date" required />
          </Field>
          <Field label="Ends">
            <Input name="ends_on" type="date" required />
          </Field>
          <div className="sm:col-span-3 flex justify-end">
            <Button type="submit" busy={addSession.isPending}>
              Add year
            </Button>
          </div>
        </form>
        <ErrorText error={addSession.error} />
      </Card>
      <Card title="Terms">
        <Table head={["Term", "Dates", ""]}>
          {terms.data?.map((t: Term) => (
            <tr key={t.id}>
              <Td>{t.label}</Td>
              <Td>
                {formatDate(t.starts_on)} – {formatDate(t.ends_on)}
              </Td>
              <Td>
                {t.is_current ? (
                  <Badge tone="green">current</Badge>
                ) : (
                  <Button variant="ghost" onClick={() => makeCurrent.mutate(t.id)}>
                    Make current
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = form(e);
            addTerm.mutate({
              ...f,
              session: Number(f.session),
              number: Number(f.number),
              next_term_begins: f.next_term_begins || null,
            });
          }}
          className="mt-3 grid gap-2 sm:grid-cols-2"
        >
          <Field label="Year">
            <Select name="session" required>
              {sessions.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Term">
            <Select name="number">
              <option value="1">First term</option>
              <option value="2">Second term</option>
              <option value="3">Third term</option>
            </Select>
          </Field>
          <Field label="Starts">
            <Input name="starts_on" type="date" required />
          </Field>
          <Field label="Ends">
            <Input name="ends_on" type="date" required />
          </Field>
          <Field label="Next term begins (for report cards)">
            <Input name="next_term_begins" type="date" />
          </Field>
          <div className="flex items-end justify-end">
            <Button type="submit" busy={addTerm.isPending}>
              Add term
            </Button>
          </div>
        </form>
        <ErrorText error={addTerm.error ?? makeCurrent.error} />
      </Card>
    </div>
  );
}

function ClassesSetup() {
  const client = useQueryClient();
  const levels = useQuery({
    queryKey: ["levels"],
    queryFn: () => api.get<Level[]>("/api/v1/academics/levels"),
  });
  const arms = useArms();
  const subjects = useSubjects();
  const toggle = useMutation({
    mutationFn: (l: Level) => api.patch(`/api/v1/academics/levels/${l.id}`, { is_active: !l.is_active }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["levels"] });
      client.invalidateQueries({ queryKey: ["arms"] });
    },
  });
  const addArm = useMutation({
    mutationFn: (b: unknown) => api.post("/api/v1/academics/arms", b),
    onSuccess: () => client.invalidateQueries({ queryKey: ["arms"] }),
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Levels and classes">
        <p className="mb-2 text-xs text-neutral-500">Switch off levels your school doesn't run.</p>
        <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
          {levels.data?.map((l) => (
            <li key={l.id} className="flex items-center justify-between py-1.5">
              <span className={l.is_active ? "" : "text-neutral-400 line-through"}>
                {l.name}{" "}
                <span className="text-xs text-neutral-500">
                  {arms.data
                    ?.filter((a) => a.level === l.id)
                    .map((a) => a.name)
                    .join(", ")}
                </span>
              </span>
              <Button variant="ghost" onClick={() => toggle.mutate(l)}>
                {l.is_active ? "Turn off" : "Turn on"}
              </Button>
            </li>
          ))}
        </ul>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const f = Object.fromEntries(new FormData(e.currentTarget));
            addArm.mutate({ level: Number(f.level), name: f.name });
          }}
          className="mt-3 flex items-end gap-2"
        >
          <Field label="Add a stream to">
            <Select name="level">
              {levels.data
                ?.filter((l) => l.is_active)
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
            </Select>
          </Field>
          <Field label="Stream">
            <Input name="name" placeholder="B" className="w-20" required />
          </Field>
          <Button type="submit" busy={addArm.isPending}>
            Add
          </Button>
        </form>
        <ErrorText error={addArm.error ?? toggle.error} />
      </Card>
      <Card title="Subjects (GES curriculum)">
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {subjects.data?.map((s) => (
            <li key={s.id}>
              <span className="font-mono text-xs text-neutral-500">{s.code}</span> {s.name}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function useStaff() {
  return useQuery({ queryKey: ["members"], queryFn: () => api.get<Member[]>("/api/v1/members") });
}

function TeacherAssignments() {
  const client = useQueryClient();
  const staff = useStaff();
  const arms = useArms();
  const subjects = useSubjects();
  const assignments = useQuery({
    queryKey: ["assignments"],
    queryFn: () => api.get<Assignment[]>("/api/v1/academics/assignments"),
  });
  const teachers = useMemo(
    () => (staff.data ?? []).filter((m) => ["teacher", "form_teacher"].includes(m.role) && m.is_active),
    [staff.data],
  );
  const name = (id: string) => {
    const m = staff.data?.find((x) => x.user === id);
    return m ? `${m.first_name} ${m.last_name}`.trim() || m.email : "Unknown";
  };
  const refresh = () => client.invalidateQueries({ queryKey: ["assignments"] });
  const add = useMutation({
    mutationFn: (b: unknown) => api.post("/api/v1/academics/assignments", b),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/academics/assignments/${id}`),
    onSuccess: refresh,
  });

  return (
    <Card title="Who teaches what">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const f = Object.fromEntries(new FormData(e.currentTarget));
          add.mutate({
            teacher_user_id: f.teacher,
            arm: f.arm,
            subject: f.subject ? Number(f.subject) : null,
            is_form_teacher: !f.subject,
          });
        }}
        className="mb-4 grid gap-2 sm:grid-cols-4 sm:items-end"
      >
        <Field label="Teacher">
          <Select name="teacher" required>
            {[...new Map(teachers.map((t) => [t.user, t])).values()].map((t) => (
              <option key={t.user} value={t.user}>
                {`${t.first_name} ${t.last_name}`.trim() || t.email}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Class">
          <Select name="arm" required>
            {arms.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Subject">
          <Select name="subject">
            <option value="">Class teacher (register &amp; comments)</option>
            {subjects.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" busy={add.isPending}>
          Assign
        </Button>
      </form>
      <ErrorText error={add.error ?? remove.error} />
      {assignments.data?.length ? (
        <Table head={["Teacher", "Class", "Subject", ""]}>
          {assignments.data.map((a) => (
            <tr key={a.id}>
              <Td>{name(a.teacher_user_id)}</Td>
              <Td>{a.arm_label}</Td>
              <Td>{a.subject_name ?? <Badge tone="blue">class teacher</Badge>}</Td>
              <Td>
                <Button variant="ghost" onClick={() => remove.mutate(a.id)}>
                  Remove
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No assignments yet. Teachers only see the classes they're assigned to.</Empty>
      )}
    </Card>
  );
}

/**
 * Leaders (academics.manage) keep every class's timetable. Teachers see their
 * week and keep the timetable of the classes they teach (academics.timetable_own).
 */
function Timetable({ leader }: { leader: boolean }) {
  const client = useQueryClient();
  const { me, can } = useSchool();
  const term = useCurrentTerm();
  const arms = useArms(!leader);
  const [arm, setArm] = useState("");
  const subjects = useSubjects(arm || undefined);
  const editable = Boolean(arm) && (leader || can(PERM.ACADEMICS_TIMETABLE_OWN));
  const staff = useQuery({
    queryKey: ["members"],
    queryFn: () => api.get<Member[]>("/api/v1/members"),
    enabled: leader,
  });
  const filter = arm ? `&arm=${arm}` : "&teacher=me";
  const periods = useQuery({
    queryKey: ["periods", term.data?.id, arm || "me"],
    queryFn: () => api.get<Period[]>(`/api/v1/academics/periods?term=${term.data?.id}${filter}`),
    enabled: Boolean(term.data) && (!leader || Boolean(arm)),
  });
  const add = useMutation({
    mutationFn: (b: unknown) => api.post("/api/v1/academics/periods", b),
    onSuccess: () => client.invalidateQueries({ queryKey: ["periods"] }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/academics/periods/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["periods"] }),
  });

  if (!term.data) return <Empty>Set a current term first.</Empty>;
  const byDay = (day: number) =>
    (periods.data ?? [])
      .filter((p) => p.weekday === day)
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-xs">
        <Field
          label="Class"
          hint={leader ? undefined : "Choose one of your classes to change its timetable."}
        >
          <Select value={arm} onChange={(e) => setArm(e.target.value)}>
            <option value="">{leader ? "Choose a class" : "My week"}</option>
            {arms.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        {[1, 2, 3, 4, 5].map((day) => (
          <Card key={day} title={DAYS[day]}>
            {byDay(day).length ? (
              <ul className="flex flex-col gap-2 text-sm">
                {byDay(day).map((p) => (
                  <li key={p.id} className="rounded-md bg-neutral-50 p-2 dark:bg-neutral-800">
                    <div className="font-medium">{p.subject_name}</div>
                    <div className="text-xs text-neutral-500">
                      {p.starts_at.slice(0, 5)}–{p.ends_at.slice(0, 5)} {!arm && `· ${p.arm_label}`}{" "}
                      {p.room && `· ${p.room}`}
                    </div>
                    <JoinLink url={p.video_url} label="Lesson" />
                    {editable && (
                      <button
                        type="button"
                        className="text-xs text-red-700 underline dark:text-red-400"
                        onClick={() => remove.mutate(p.id)}
                        aria-label={`Remove ${p.subject_name} on ${DAYS[day]} at ${p.starts_at.slice(0, 5)}`}
                      >
                        Remove
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-neutral-400">Free</p>
            )}
          </Card>
        ))}
      </div>
      {editable && (
        <Card title="Add a period">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = Object.fromEntries(new FormData(e.currentTarget));
              const teacher = leader ? f.teacher || null : f.mine ? me.data?.id : null;
              add.mutate({
                term: term.data?.id,
                arm,
                subject: Number(f.subject),
                weekday: Number(f.weekday),
                starts_at: f.starts_at,
                ends_at: f.ends_at,
                teacher_user_id: teacher,
                room: f.room,
                video_url: f.video_url ?? "",
              });
            }}
            className="grid gap-2 sm:grid-cols-6 sm:items-end"
          >
            <Field label="Day">
              <Select name="weekday">
                {[1, 2, 3, 4, 5].map((d) => (
                  <option key={d} value={d}>
                    {DAYS[d]}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Starts">
              <Input name="starts_at" type="time" defaultValue="08:00" required />
            </Field>
            <Field label="Ends">
              <Input name="ends_at" type="time" defaultValue="08:40" required />
            </Field>
            <Field label="Subject">
              <Select name="subject" required>
                {subjects.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            </Field>
            {leader ? (
              <Field label="Teacher">
                <Select name="teacher">
                  <option value="">—</option>
                  {[
                    ...new Map(
                      (staff.data ?? [])
                        .filter((m) => ["teacher", "form_teacher"].includes(m.role))
                        .map((m) => [m.user, m]),
                    ).values(),
                  ].map((m) => (
                    <option key={m.user} value={m.user}>
                      {`${m.first_name} ${m.last_name}`.trim() || m.email}
                    </option>
                  ))}
                </Select>
              </Field>
            ) : (
              <label className="flex items-center gap-2 pb-2 text-sm">
                <input type="checkbox" name="mine" defaultChecked className="size-4 accent-brand" />I teach
                this period
              </label>
            )}
            <div className="sm:col-span-5">
              <Field
                label="Online lesson link (optional)"
                hint="For lessons taught online; starts with https://"
              >
                <Input name="video_url" type="url" inputMode="url" maxLength={500} pattern="https://.*" />
              </Field>
            </div>
            <Button type="submit" busy={add.isPending}>
              Add
            </Button>
          </form>
          <ErrorText error={add.error ?? remove.error} />
        </Card>
      )}
    </div>
  );
}
