"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useArms, useSchool, useSubjects } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Question = {
  id?: number;
  kind: "choice" | "true_false" | "short";
  text: string;
  options: string[];
  answer?: number | null;
  marks: number;
};
type OnlineTest = {
  id: string;
  arm_name: string;
  subject_name: string;
  title: string;
  instructions: string;
  opens_at: string;
  closes_at: string;
  minutes: number;
  published: boolean;
  results_released: boolean;
  question_count: number;
  total_marks: number;
  questions?: Question[];
};
type ResultRow = {
  student: string;
  name: string;
  attempt: string | null;
  status: string;
  score: number | null;
  answers: Record<string, unknown>;
  awarded: Record<string, number>;
};
type Sitting = { attempt: string; ends_at: string; answers: Record<string, unknown>; questions: Question[] };
type Mine = {
  test: string;
  title: string;
  subject: string;
  student: string;
  score: number | null;
  out_of: number;
  closed: string;
};

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
const toLocalInput = (d: Date) =>
  new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

/** Online tests: teachers write and mark them, pupils sit them, families see results. */
export default function TestsPage() {
  const { can } = useSchool();
  if (can(PERM.LMS_TEACH, PERM.LMS_MANAGE)) return <TeacherView />;
  if (can(PERM.LMS_LEARN)) return <PupilView />;
  return <FamilyView />;
}

function useTests() {
  return useQuery({
    queryKey: ["online-tests"],
    queryFn: () => api.get<OnlineTest[]>("/api/v1/exams/tests"),
  });
}

function FamilyView() {
  const mine = useQuery({
    queryKey: ["test-results"],
    queryFn: () => api.get<Mine[]>("/api/v1/exams/tests/mine"),
  });
  return (
    <>
      <PageHeader
        title="Online tests"
        description="Your children's online test results, once teachers release them."
      />
      <ErrorText error={mine.error} />
      {mine.data?.length ? (
        <Table head={["Child", "Test", "Subject", "Score"]}>
          {mine.data.map((m) => (
            <tr key={`${m.test}-${m.student}`}>
              <Td>{m.student}</Td>
              <Td className="font-medium">{m.title}</Td>
              <Td>{m.subject}</Td>
              <Td className="tabular-nums">
                {m.score ?? "—"} / {m.out_of}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No results yet.</Empty>
      )}
    </>
  );
}

function PupilView() {
  const tests = useTests();
  const mine = useQuery({
    queryKey: ["test-results"],
    queryFn: () => api.get<Mine[]>("/api/v1/exams/tests/mine"),
  });
  const [sitting, setSitting] = useState<OnlineTest | null>(null);
  const now = Date.now();
  return (
    <>
      <PageHeader
        title="Online tests"
        description="Tests your teachers have set. You can sit each one once."
      />
      <ErrorText error={tests.error} />
      {tests.isPending ? (
        <Loading />
      ) : tests.data?.length ? (
        <ul className="flex flex-col gap-3">
          {tests.data.map((t) => {
            const open = new Date(t.opens_at).getTime() <= now && now < new Date(t.closes_at).getTime();
            const result = mine.data?.find((m) => m.test === t.id);
            return (
              <li key={t.id}>
                <Card title={t.title}>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">
                    {t.subject_name} · {t.question_count} questions · {t.minutes} minutes · open{" "}
                    {when(t.opens_at)} to {when(t.closes_at)}
                  </p>
                  <div className="mt-3">
                    {result ? (
                      <Badge tone="green">{`Score ${result.score ?? "—"} / ${result.out_of}`}</Badge>
                    ) : open ? (
                      <Button onClick={() => setSitting(t)}>Start or carry on</Button>
                    ) : (
                      <Badge tone="grey">
                        {now < new Date(t.opens_at).getTime() ? "Not open yet" : "Closed"}
                      </Badge>
                    )}
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      ) : (
        <Empty>No tests set.</Empty>
      )}
      <Modal open={sitting !== null} onClose={() => setSitting(null)} title={sitting?.title ?? ""}>
        {sitting && <Sit test={sitting} onDone={() => setSitting(null)} />}
      </Modal>
    </>
  );
}

function Sit({ test, onDone }: { test: OnlineTest; onDone: () => void }) {
  const client = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [left, setLeft] = useState<number | null>(null);
  const start = useQuery({
    queryKey: ["sitting", test.id],
    queryFn: () => api.post<Sitting>(`/api/v1/exams/tests/${test.id}/start`),
    retry: false,
  });
  const save = useMutation({
    mutationFn: (a: Record<string, unknown>) =>
      api.post(`/api/v1/exams/tests/${test.id}/save`, { answers: a }),
  });
  const submit = useMutation({
    mutationFn: () => api.post(`/api/v1/exams/tests/${test.id}/submit`, { answers }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["online-tests"] });
      void client.invalidateQueries({ queryKey: ["test-results"] });
      onDone();
    },
  });
  useEffect(() => {
    if (start.data) setAnswers(start.data.answers);
  }, [start.data]);
  useEffect(() => {
    if (!start.data) return;
    const end = new Date(start.data.ends_at).getTime();
    const tick = () => setLeft(Math.max(0, Math.round((end - Date.now()) / 1000)));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [start.data]);
  const set = (qid: number | undefined, value: unknown) => {
    if (qid === undefined) return;
    const next = { ...answers, [String(qid)]: value };
    setAnswers(next);
    save.mutate(next);
  };
  if (start.isPending) return <Loading />;
  if (start.error) return <ErrorText error={start.error} />;
  const s = start.data;
  return (
    <div className="flex flex-col gap-4 text-sm">
      <p role="timer" aria-live="off" className="font-medium tabular-nums">
        Time left: {left === null ? "…" : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`}
      </p>
      {left === 0 && <Alert tone="warning">Time is up. Hand in what you have.</Alert>}
      {s?.questions.map((q, i) => (
        <fieldset
          key={q.id}
          className="rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
        >
          <legend className="px-1 font-medium">
            {i + 1}. {q.text}{" "}
            <span className="text-neutral-600 dark:text-neutral-400">
              ({q.marks} mark{q.marks === 1 ? "" : "s"})
            </span>
          </legend>
          {q.kind === "short" ? (
            <Textarea
              aria-label={`Answer to question ${i + 1}`}
              rows={3}
              defaultValue={String(answers[String(q.id)] ?? "")}
              onBlur={(e) => set(q.id, e.target.value)}
              disabled={left === 0}
            />
          ) : (
            <div className="flex flex-col gap-1">
              {q.options.map((o, j) => (
                <label key={o} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`q-${q.id}`}
                    className="size-4 accent-brand"
                    checked={answers[String(q.id)] === j}
                    onChange={() => set(q.id, j)}
                    disabled={left === 0}
                  />
                  {o}
                </label>
              ))}
            </div>
          )}
        </fieldset>
      ))}
      <ErrorText error={submit.error} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-neutral-600 dark:text-neutral-400">
          {save.isPending ? "Saving…" : "Your answers save as you go."}
        </span>
        <Button busy={submit.isPending} onClick={() => submit.mutate()}>
          Hand in
        </Button>
      </div>
    </div>
  );
}

function TeacherView() {
  const tests = useTests();
  const [writing, setWriting] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <PageHeader
        title="Online tests"
        description="Write a test, publish it for a class, then mark short answers and release the results."
        actions={<Button onClick={() => setWriting(true)}>New test</Button>}
      />
      <ErrorText error={tests.error} />
      {tests.isPending ? (
        <Loading />
      ) : tests.data?.length ? (
        <Table head={["Test", "Class", "Opens", "Questions", "Status", ""]}>
          {tests.data.map((t) => (
            <tr key={t.id}>
              <Td className="font-medium">{t.title}</Td>
              <Td>
                {t.arm_name}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">{t.subject_name}</span>
              </Td>
              <Td className="whitespace-nowrap">{when(t.opens_at)}</Td>
              <Td className="tabular-nums">
                {t.question_count} ({t.total_marks} marks)
              </Td>
              <Td>
                {t.results_released ? (
                  <Badge tone="green">Results out</Badge>
                ) : t.published ? (
                  <Badge tone="blue">Published</Badge>
                ) : (
                  <Badge tone="amber">Draft</Badge>
                )}
              </Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(t.id)} aria-label={`Open ${t.title}`}>
                  Open
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No tests yet.</Empty>
      )}
      <Modal open={writing} onClose={() => setWriting(false)} title="New test">
        {writing && (
          <NewTest
            onDone={(id) => {
              setWriting(false);
              setOpen(id);
            }}
          />
        )}
      </Modal>
      <Modal open={open !== null} onClose={() => setOpen(null)} title="Test">
        {open && <TestDetail id={open} />}
      </Modal>
    </>
  );
}

function NewTest({ onDone }: { onDone: (id: string) => void }) {
  const client = useQueryClient();
  const arms = useArms(true);
  const [arm, setArm] = useState("");
  const subjects = useSubjects(arm || undefined);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<OnlineTest>("/api/v1/exams/tests", body),
    onSuccess: (t) => {
      void client.invalidateQueries({ queryKey: ["online-tests"] });
      onDone(t.id);
    },
  });
  const inAnHour = new Date(Date.now() + 3600_000);
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
        save.mutate({
          arm,
          subject: Number(f.subject),
          title: f.title,
          instructions: f.instructions,
          opens_at: new Date(f.opens_at ?? "").toISOString(),
          closes_at: new Date(f.closes_at ?? "").toISOString(),
          minutes: Number(f.minutes),
        });
      }}
    >
      <Field label="Class">
        <Select required value={arm} onChange={(e) => setArm(e.target.value)}>
          <option value="" disabled>
            Choose
          </option>
          {arms.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Subject">
        <Select name="subject" required defaultValue="" disabled={!arm}>
          <option value="" disabled>
            Choose
          </option>
          {subjects.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Field label="Title">
          <Input name="title" required maxLength={140} />
        </Field>
      </div>
      <Field label="Opens">
        <Input name="opens_at" type="datetime-local" required defaultValue={toLocalInput(new Date())} />
      </Field>
      <Field label="Closes">
        <Input name="closes_at" type="datetime-local" required defaultValue={toLocalInput(inAnHour)} />
      </Field>
      <Field label="Minutes allowed">
        <Input name="minutes" type="number" min={1} max={300} required defaultValue={30} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Instructions (optional)">
          <Textarea name="instructions" maxLength={2000} rows={2} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Next: add questions
        </Button>
      </div>
    </form>
  );
}

function TestDetail({ id }: { id: string }) {
  const client = useQueryClient();
  const test = useQuery({
    queryKey: ["online-test", id],
    queryFn: () => api.get<OnlineTest>(`/api/v1/exams/tests/${id}`),
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["online-test", id] });
    void client.invalidateQueries({ queryKey: ["online-tests"] });
  };
  const act = useMutation({
    mutationFn: (what: "publish" | "release") => api.post(`/api/v1/exams/tests/${id}/${what}`),
    onSuccess: refresh,
  });
  if (!test.data) return test.error ? <ErrorText error={test.error} /> : <Loading />;
  const t = test.data;
  return (
    <div className="flex flex-col gap-4 text-sm">
      <p className="text-neutral-600 dark:text-neutral-300">
        {t.title} · {t.arm_name} · {t.subject_name} · {when(t.opens_at)} to {when(t.closes_at)} · {t.minutes}{" "}
        minutes
      </p>
      {!t.published ? (
        <>
          <QuestionEditor id={id} initial={t.questions ?? []} onSaved={refresh} />
          <ErrorText error={act.error} />
          <div className="flex justify-end">
            <Button busy={act.isPending} onClick={() => act.mutate("publish")} disabled={!t.question_count}>
              Publish for the class
            </Button>
          </div>
        </>
      ) : (
        <>
          <Results test={t} />
          <ErrorText error={act.error} />
          {!t.results_released && (
            <div className="flex justify-end">
              <Button busy={act.isPending} onClick={() => act.mutate("release")}>
                Release results to pupils and parents
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function QuestionEditor({ id, initial, onSaved }: { id: string; initial: Question[]; onSaved: () => void }) {
  const [questions, setQuestions] = useState<Question[]>(
    initial.length ? initial : [{ kind: "choice", text: "", options: ["", ""], answer: 0, marks: 1 }],
  );
  const save = useMutation({
    mutationFn: () =>
      api.put(
        `/api/v1/exams/tests/${id}/questions`,
        questions.map(({ id: _id, ...q }) => q),
      ),
    onSuccess: onSaved,
  });
  const set = (i: number, patch: Partial<Question>) =>
    setQuestions((all) => all.map((q, j) => (j === i ? { ...q, ...patch } : q)));
  return (
    <section aria-labelledby="questions-title" className="flex flex-col gap-3">
      <h3 id="questions-title" className="font-medium">
        Questions
      </h3>
      {questions.map((q, i) => (
        <fieldset
          // biome-ignore lint/suspicious/noArrayIndexKey: questions are edited in place; order is the identity.
          key={i}
          className="flex flex-col gap-2 rounded-control border border-neutral-200 p-3 dark:border-neutral-800"
        >
          <legend className="px-1 font-medium">Question {i + 1}</legend>
          <div className="grid gap-2 sm:grid-cols-[1fr_10rem_5rem]">
            <Field label="Question">
              <Input value={q.text} onChange={(e) => set(i, { text: e.target.value })} />
            </Field>
            <Field label="Kind">
              <Select
                value={q.kind}
                onChange={(e) => {
                  const kind = e.target.value as Question["kind"];
                  set(i, {
                    kind,
                    options: kind === "true_false" ? ["True", "False"] : kind === "short" ? [] : ["", ""],
                    answer: kind === "short" ? null : 0,
                  });
                }}
              >
                <option value="choice">Choose one</option>
                <option value="true_false">True or false</option>
                <option value="short">Short answer</option>
              </Select>
            </Field>
            <Field label="Marks">
              <Input
                type="number"
                min={1}
                max={100}
                value={q.marks}
                onChange={(e) => set(i, { marks: Number(e.target.value) || 1 })}
              />
            </Field>
          </div>
          {q.kind !== "short" && (
            <div className="flex flex-col gap-1">
              {q.options.map((o, j) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: options are edited in place.
                <div key={j} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`right-${i}`}
                    className="size-4 accent-brand"
                    checked={q.answer === j}
                    onChange={() => set(i, { answer: j })}
                    aria-label={`Choice ${j + 1} is right`}
                  />
                  {q.kind === "true_false" ? (
                    <span>{o}</span>
                  ) : (
                    <Input
                      aria-label={`Choice ${j + 1}`}
                      value={o}
                      onChange={(e) =>
                        set(i, { options: q.options.map((x, k) => (k === j ? e.target.value : x)) })
                      }
                    />
                  )}
                </div>
              ))}
              {q.kind === "choice" && q.options.length < 6 && (
                <div>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => set(i, { options: [...q.options, ""] })}
                  >
                    Add a choice
                  </Button>
                </div>
              )}
            </div>
          )}
          <div className="flex justify-end">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setQuestions((all) => all.filter((_, j) => j !== i))}
            >
              Remove question
            </Button>
          </div>
        </fieldset>
      ))}
      <div className="flex flex-wrap justify-between gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={() =>
            setQuestions((all) => [
              ...all,
              { kind: "choice", text: "", options: ["", ""], answer: 0, marks: 1 },
            ])
          }
        >
          Add a question
        </Button>
        <Button type="button" busy={save.isPending} onClick={() => save.mutate()}>
          Save questions
        </Button>
      </div>
      <ErrorText error={save.error} />
      {save.isSuccess && <Alert tone="success">Questions saved.</Alert>}
    </section>
  );
}

function Results({ test }: { test: OnlineTest }) {
  const client = useQueryClient();
  const results = useQuery({
    queryKey: ["test-results-staff", test.id],
    queryFn: () => api.get<ResultRow[]>(`/api/v1/exams/tests/${test.id}/results`),
  });
  const detail = useQuery({
    queryKey: ["online-test", test.id],
    queryFn: () => api.get<OnlineTest>(`/api/v1/exams/tests/${test.id}`),
  });
  const mark = useMutation({
    mutationFn: ({ attempt, awarded }: { attempt: string; awarded: Record<string, number> }) =>
      api.post(`/api/v1/exams/tests/${test.id}/attempts/${attempt}/mark`, { awarded }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["test-results-staff", test.id] }),
  });
  const short = (detail.data?.questions ?? []).filter((q) => q.kind === "short");
  return (
    <>
      <ErrorText error={results.error ?? mark.error} />
      {results.data ? (
        <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
          {results.data.map((r) => (
            <li key={r.student} className="py-2">
              <div className="flex justify-between gap-2">
                <span className="font-medium">{r.name}</span>
                <span className="tabular-nums">
                  {r.attempt ? `${r.score ?? 0} / ${test.total_marks}` : "Not sat"}{" "}
                  {r.status === "submitted" && <Badge tone="amber">To mark</Badge>}
                </span>
              </div>
              {r.attempt && r.status !== "started" && short.length > 0 && (
                <form
                  className="mt-2 flex flex-col gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    const awarded: Record<string, number> = {};
                    for (const q of short) awarded[String(q.id)] = Number(f.get(`q-${q.id}`) ?? 0);
                    if (r.attempt) mark.mutate({ attempt: r.attempt, awarded });
                  }}
                >
                  {short.map((q) => (
                    <div key={q.id} className="grid gap-2 sm:grid-cols-[1fr_6rem] sm:items-end">
                      <p>
                        <span className="text-neutral-600 dark:text-neutral-400">{q.text}</span>
                        <span className="block">{String(r.answers[String(q.id)] ?? "No answer")}</span>
                      </p>
                      <Field label={`Marks (of ${q.marks})`}>
                        <Input
                          name={`q-${q.id}`}
                          type="number"
                          min={0}
                          max={q.marks}
                          defaultValue={r.awarded[String(q.id)] ?? ""}
                        />
                      </Field>
                    </div>
                  ))}
                  <div className="flex justify-end">
                    <Button type="submit" variant="secondary" busy={mark.isPending}>
                      Save marks for {r.name}
                    </Button>
                  </div>
                </form>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Loading />
      )}
      <p className="text-xs text-neutral-600 dark:text-neutral-400">Closes {formatDate(test.closes_at)}.</p>
    </>
  );
}
