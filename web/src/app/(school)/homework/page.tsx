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
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { JoinLink } from "@/components/video-link";
import { api, download } from "@/lib/api";
import { formatDate, todayInAccra } from "@/lib/format";
import { useArms, useSchool, useSubjects } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Submission = {
  id: string;
  student: string;
  student_name: string;
  text: string;
  file_name: string;
  has_file: boolean;
  submitted_at: string;
  late: boolean;
  score: number | null;
  feedback: string;
  marked_at: string | null;
};
type Homework = {
  id: string;
  arm: string;
  arm_name: string;
  subject: number;
  subject_name: string;
  title: string;
  instructions: string;
  due_on: string;
  max_score: number | null;
  hand_in_online: boolean;
  attachment_name: string;
  has_attachment: boolean;
  video_url: string;
  set_by_name: string;
  handed_in: number | null;
  mine?: Submission[];
};
type Material = {
  id: string;
  arm_name: string;
  subject_name: string;
  title: string;
  note: string;
  link: string;
  file_name: string;
  has_file: boolean;
  created_at: string;
};
type SheetRow = { student: string; name: string; submission: Submission | null };

/** Homework: teachers set and mark it, pupils hand it in, parents follow it. */
export default function HomeworkPage() {
  const { can, roles } = useSchool();
  const teacher = can(PERM.LMS_TEACH, PERM.LMS_MANAGE);
  const [tab, setTab] = useState<"homework" | "materials">("homework");
  return (
    <>
      <PageHeader
        title="Homework"
        description={
          teacher
            ? "Set homework for your classes, see who handed it in, and mark it."
            : roles.includes("parent")
              ? "Your children's homework, what they handed in, and their teachers' feedback."
              : "Your homework and learning materials."
        }
      />
      <div
        role="tablist"
        aria-label="Homework"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {(
          [
            ["homework", "Homework"],
            ["materials", "Learning materials"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${tab === key ? "border-brand font-medium" : "border-transparent text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "homework" && (teacher ? <TeacherHomework /> : <FamilyHomework />)}
        {tab === "materials" && <Materials teacher={teacher} />}
      </div>
    </>
  );
}

function useHomework() {
  return useQuery({ queryKey: ["homework"], queryFn: () => api.get<Homework[]>("/api/v1/lms/homework") });
}

function fileLink(path: string, name: string) {
  return () => void download(path, name);
}

function TeacherHomework() {
  const homework = useHomework();
  const [setting, setSetting] = useState(false);
  const [open, setOpen] = useState<Homework | null>(null);
  return (
    <>
      <div className="mb-4 flex justify-end">
        <Button onClick={() => setSetting(true)}>Set homework</Button>
      </div>
      <ErrorText error={homework.error} />
      {homework.isPending ? (
        <Loading />
      ) : homework.data?.length ? (
        <Table head={["Due", "Class", "Homework", "Handed in", ""]}>
          {homework.data.map((h) => (
            <tr key={h.id}>
              <Td className="whitespace-nowrap">
                {formatDate(h.due_on)} {h.due_on < todayInAccra() && <Badge tone="grey">Past</Badge>}
              </Td>
              <Td>
                {h.arm_name}
                <span className="block text-xs text-neutral-600 dark:text-neutral-400">{h.subject_name}</span>
              </Td>
              <Td className="font-medium">{h.title}</Td>
              <Td className="tabular-nums">{h.hand_in_online ? (h.handed_in ?? 0) : "On paper"}</Td>
              <Td className="text-right">
                <Button variant="ghost" onClick={() => setOpen(h)} aria-label={`Open ${h.title}`}>
                  Open
                </Button>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No homework set yet.</Empty>
      )}
      <Modal open={setting} onClose={() => setSetting(false)} title="Set homework">
        {setting && <SetHomework onDone={() => setSetting(false)} />}
      </Modal>
      <Modal open={open !== null} onClose={() => setOpen(null)} title={open?.title ?? ""}>
        {open && <Marking homework={open} />}
      </Modal>
    </>
  );
}

function ClassSubjectFields() {
  const { can } = useSchool();
  const arms = useArms(!can(PERM.LMS_MANAGE));
  const [arm, setArm] = useState("");
  const subjects = useSubjects(arm || undefined);
  return (
    <>
      <Field label="Class">
        <Select name="arm" required value={arm} onChange={(e) => setArm(e.target.value)}>
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
    </>
  );
}

function SetHomework({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (form: FormData) => api.post("/api/v1/lms/homework", form),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["homework"] });
      onDone();
    },
  });
  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        form.set("hand_in_online", form.get("hand_in_online") === "on" ? "true" : "false");
        if (!form.get("max_score")) form.delete("max_score");
        if (!(form.get("file") as File | null)?.size) form.delete("file");
        if (!form.get("video_url")) form.delete("video_url");
        save.mutate(form);
      }}
    >
      <ClassSubjectFields />
      <div className="sm:col-span-2">
        <Field label="Title">
          <Input name="title" required maxLength={140} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label="What to do (optional)">
          <Textarea name="instructions" maxLength={4000} rows={4} />
        </Field>
      </div>
      <Field label="Due on">
        <Input name="due_on" type="date" required min={todayInAccra()} />
      </Field>
      <Field label="Marked out of (optional)">
        <Input name="max_score" type="number" min={1} max={1000} />
      </Field>
      <Field label="Worksheet (optional)" hint="PDF, Word, picture: 5 MB at most.">
        <Input name="file" type="file" />
      </Field>
      <Field
        label="Online lesson link (optional)"
        hint="Google Meet, Zoom, Teams or WhatsApp; starts with https://"
      >
        <Input name="video_url" type="url" inputMode="url" maxLength={500} pattern="https://.*" />
      </Field>
      <label className="flex items-center gap-2 self-end pb-2 text-sm">
        <input type="checkbox" name="hand_in_online" defaultChecked className="size-4 accent-brand" /> Pupils
        hand it in here
      </label>
      <div className="sm:col-span-2">
        <ErrorText error={save.error} />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" busy={save.isPending}>
          Set homework
        </Button>
      </div>
    </form>
  );
}

function Marking({ homework }: { homework: Homework }) {
  const client = useQueryClient();
  const sheet = useQuery({
    queryKey: ["homework-sheet", homework.id],
    queryFn: () => api.get<SheetRow[]>(`/api/v1/lms/homework/${homework.id}/submissions`),
    enabled: homework.hand_in_online,
  });
  const mark = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.post(`/api/v1/lms/submissions/${id}/mark`, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["homework-sheet", homework.id] });
    },
  });
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="text-neutral-600 dark:text-neutral-300">
        {homework.arm_name} · {homework.subject_name} · due {formatDate(homework.due_on)}
      </p>
      {homework.instructions && <p className="whitespace-pre-wrap">{homework.instructions}</p>}
      <JoinLink url={homework.video_url} label="Online lesson" />
      {homework.has_attachment && (
        <div>
          <Button
            variant="secondary"
            onClick={fileLink(`/api/v1/lms/homework/${homework.id}/attachment`, homework.attachment_name)}
          >
            Worksheet: {homework.attachment_name}
          </Button>
        </div>
      )}
      {!homework.hand_in_online ? (
        <Alert>Handed in on paper.</Alert>
      ) : sheet.isPending ? (
        <Loading />
      ) : (
        <ul className="divide-y divide-neutral-100 dark:divide-neutral-800">
          {sheet.data?.map((r) => (
            <li key={r.student} className="py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{r.name}</span>
                {r.submission ? (
                  <span className="flex items-center gap-2">
                    {r.submission.late && <Badge tone="amber">Late</Badge>}
                    {r.submission.marked_at ? (
                      <Badge tone="green">{`Marked${r.submission.score !== null ? `: ${r.submission.score}${homework.max_score ? `/${homework.max_score}` : ""}` : ""}`}</Badge>
                    ) : (
                      <Badge tone="blue">Handed in</Badge>
                    )}
                  </span>
                ) : (
                  <span className="text-neutral-600 dark:text-neutral-400">Not handed in</span>
                )}
              </div>
              {r.submission && (
                <>
                  {r.submission.text && <p className="mt-1 whitespace-pre-wrap">{r.submission.text}</p>}
                  {r.submission.has_file && (
                    <Button
                      variant="ghost"
                      onClick={fileLink(
                        `/api/v1/lms/submissions/${r.submission.id}/file`,
                        r.submission.file_name,
                      )}
                    >
                      {r.submission.file_name}
                    </Button>
                  )}
                  <form
                    className="mt-2 grid gap-2 sm:grid-cols-[6rem_1fr_auto] sm:items-end"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
                      if (!r.submission) return;
                      mark.mutate({
                        id: r.submission.id,
                        body: { score: f.score ? Number(f.score) : null, feedback: f.feedback },
                      });
                    }}
                  >
                    <Field label="Mark">
                      <Input
                        name="score"
                        type="number"
                        min={0}
                        max={homework.max_score ?? 1000}
                        defaultValue={r.submission.score ?? ""}
                      />
                    </Field>
                    <Field label={`Feedback for ${r.name}`}>
                      <Input name="feedback" maxLength={1000} defaultValue={r.submission.feedback} />
                    </Field>
                    <Button
                      type="submit"
                      variant="secondary"
                      busy={mark.isPending && mark.variables?.id === r.submission.id}
                    >
                      Save mark
                    </Button>
                  </form>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <ErrorText error={sheet.error ?? mark.error} />
    </div>
  );
}

function FamilyHomework() {
  const { can } = useSchool();
  const pupil = can(PERM.LMS_LEARN);
  const homework = useHomework();
  const [handing, setHanding] = useState<Homework | null>(null);
  return (
    <>
      <ErrorText error={homework.error} />
      {homework.isPending ? (
        <Loading />
      ) : homework.data?.length ? (
        <ul className="flex flex-col gap-3">
          {homework.data.map((h) => {
            const mine = h.mine ?? [];
            return (
              <li key={h.id}>
                <Card title={h.title}>
                  <p className="text-sm text-neutral-600 dark:text-neutral-300">
                    {h.subject_name} · {h.arm_name} · due {formatDate(h.due_on)} · from {h.set_by_name}
                  </p>
                  {h.instructions && <p className="mt-2 whitespace-pre-wrap text-sm">{h.instructions}</p>}
                  {h.has_attachment && (
                    <Button
                      variant="ghost"
                      onClick={fileLink(`/api/v1/lms/homework/${h.id}/attachment`, h.attachment_name)}
                    >
                      Worksheet: {h.attachment_name}
                    </Button>
                  )}
                  <div className="mt-2 text-sm">
                    {mine.length ? (
                      mine.map((s) => (
                        <p key={s.id}>
                          {s.student_name}: handed in {formatDate(s.submitted_at)}
                          {s.late ? " (late)" : ""}
                          {s.marked_at
                            ? ` · mark ${s.score ?? "—"}${h.max_score ? `/${h.max_score}` : ""}${s.feedback ? ` · “${s.feedback}”` : ""}`
                            : ""}
                        </p>
                      ))
                    ) : h.hand_in_online ? (
                      <p className="text-neutral-600 dark:text-neutral-300">Not handed in yet.</p>
                    ) : (
                      <p className="text-neutral-600 dark:text-neutral-300">Hand in on paper.</p>
                    )}
                  </div>
                  {pupil && h.hand_in_online && !mine.some((s) => s.marked_at) && (
                    <div className="mt-3">
                      <Button variant="secondary" onClick={() => setHanding(h)}>
                        {mine.length ? "Hand in again" : "Hand in"}
                      </Button>
                    </div>
                  )}
                </Card>
              </li>
            );
          })}
        </ul>
      ) : (
        <Empty>No homework.</Empty>
      )}
      <Modal
        open={handing !== null}
        onClose={() => setHanding(null)}
        title={`Hand in: ${handing?.title ?? ""}`}
      >
        {handing && <HandIn homework={handing} onDone={() => setHanding(null)} />}
      </Modal>
    </>
  );
}

function HandIn({ homework, onDone }: { homework: Homework; onDone: () => void }) {
  const client = useQueryClient();
  const send = useMutation({
    mutationFn: (form: FormData) => api.post(`/api/v1/lms/homework/${homework.id}/submit`, form),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["homework"] });
      onDone();
    },
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        if (!(form.get("file") as File | null)?.size) form.delete("file");
        send.mutate(form);
      }}
    >
      <Field label="Your answer">
        <Textarea name="text" maxLength={8000} rows={6} />
      </Field>
      <Field label="Attach your work (optional)" hint="A photo or file, 5 MB at most.">
        <Input name="file" type="file" />
      </Field>
      <ErrorText error={send.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={send.isPending}>
          Hand in
        </Button>
      </div>
    </form>
  );
}

function Materials({ teacher }: { teacher: boolean }) {
  const client = useQueryClient();
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: () => api.get<Material[]>("/api/v1/lms/materials"),
  });
  const [sharing, setSharing] = useState(false);
  const share = useMutation({
    mutationFn: (form: FormData) => api.post("/api/v1/lms/materials", form),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["materials"] });
      setSharing(false);
    },
  });
  return (
    <>
      {teacher && (
        <div className="mb-4 flex justify-end">
          <Button onClick={() => setSharing(true)}>Share something</Button>
        </div>
      )}
      <ErrorText error={materials.error} />
      {materials.isPending ? (
        <Loading />
      ) : materials.data?.length ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {materials.data.map((m) => (
            <li key={m.id}>
              <Card title={m.title}>
                <p className="text-sm text-neutral-600 dark:text-neutral-300">
                  {m.subject_name} · {m.arm_name} · {formatDate(m.created_at)}
                </p>
                {m.note && <p className="mt-2 whitespace-pre-wrap text-sm">{m.note}</p>}
                <div className="mt-2 flex flex-wrap gap-2">
                  {m.link && (
                    <a
                      href={m.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-brand-strong hover:underline dark:text-brand-sky"
                    >
                      Open the link
                    </a>
                  )}
                  {m.has_file && (
                    <Button
                      variant="ghost"
                      onClick={fileLink(`/api/v1/lms/materials/${m.id}/file`, m.file_name)}
                    >
                      {m.file_name}
                    </Button>
                  )}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Nothing shared yet.</Empty>
      )}
      <Modal open={sharing} onClose={() => setSharing(false)} title="Share with a class">
        {sharing && (
          <form
            className="grid gap-3 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              if (!(form.get("file") as File | null)?.size) form.delete("file");
              if (!form.get("link")) form.delete("link");
              share.mutate(form);
            }}
          >
            <ClassSubjectFields />
            <div className="sm:col-span-2">
              <Field label="Title">
                <Input name="title" required maxLength={140} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Note (optional)">
                <Textarea name="note" maxLength={4000} rows={3} />
              </Field>
            </div>
            <Field label="Link (optional)">
              <Input name="link" type="url" placeholder="https://" />
            </Field>
            <Field label="File (optional)">
              <Input name="file" type="file" />
            </Field>
            <div className="sm:col-span-2">
              <ErrorText error={share.error} />
            </div>
            <div className="flex justify-end sm:col-span-2">
              <Button type="submit" busy={share.isPending}>
                Share
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </>
  );
}
