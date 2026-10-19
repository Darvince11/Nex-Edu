"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Empty, ErrorText, Field, Input, Loading, PageHeader, Select } from "@/components/ui";
import { api, getSelectedSchool, rawPost } from "@/lib/api";
import { todayInAccra } from "@/lib/format";
import { useArms, useOnline, useSchool } from "@/lib/hooks";
import { enqueue, flush, type QueuedRegister, readQueue } from "@/lib/offline-queue";
import { isLeader } from "@/lib/roles";

type Row = { student: string; admission_number: string; name: string; status: string | null; note: string };
type Sheet = { arm: string; arm_label: string; date: string; rows: Row[] };
type Result = {
  created: number;
  updated: number;
  unchanged: number;
  conflicts: unknown[];
  replayed: boolean;
};

const STATUSES = [
  { value: "present", label: "P", title: "Present", tone: "bg-emerald-600" },
  { value: "late", label: "L", title: "Late", tone: "bg-amber-500" },
  { value: "absent", label: "A", title: "Absent", tone: "bg-red-600" },
  { value: "excused", label: "E", title: "Excused", tone: "bg-sky-600" },
];

const REGISTER_URL = "/api/v1/attendance/register";

export default function AttendancePage() {
  const { roles } = useSchool();
  const online = useOnline();
  const client = useQueryClient();
  const arms = useArms(!isLeader(roles));
  const [arm, setArm] = useState("");
  const [date, setDate] = useState(todayInAccra());
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ tone: "success" | "warning" | "error"; text: string } | null>(
    null,
  );
  const [pending, setPending] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!arm && arms.data?.[0]) setArm(arms.data[0].id);
  }, [arms.data, arm]);

  const sheet = useQuery({
    queryKey: ["register", arm, date],
    queryFn: () => api.get<Sheet>(`${REGISTER_URL}?arm=${arm}&date=${date}`),
    enabled: Boolean(arm) && online,
  });

  useEffect(() => {
    if (sheet.data) {
      setMarks(Object.fromEntries(sheet.data.rows.map((r) => [r.student, r.status ?? "present"])));
    }
  }, [sheet.data]);

  const sync = useCallback(async () => {
    const result = await flush((item) => rawPost(REGISTER_URL, { ...item, school: undefined }, item.school));
    setPending(result.pending);
    if (result.sent) {
      setMessage({ tone: "success", text: `${result.sent} saved register(s) were sent.` });
      client.invalidateQueries({ queryKey: ["register"] });
    }
    if (result.failed.length) {
      setMessage({
        tone: "error",
        text: "A saved register was rejected by the server. Please take it again.",
      });
    }
  }, [client]);

  useEffect(() => {
    setPending(readQueue().length);
    if (online) void sync();
  }, [online, sync]);

  const markAll = (status: string) =>
    setMarks(Object.fromEntries((sheet.data?.rows ?? []).map((r) => [r.student, status])));

  async function save() {
    const school = getSelectedSchool();
    if (!school || !sheet.data) return;
    const item: QueuedRegister = {
      batch_id: crypto.randomUUID(),
      school,
      arm,
      date,
      recorded_at: new Date().toISOString(),
      entries: Object.entries(marks).map(([student, status]) => ({ student, status })),
    };
    setSaving(true);
    try {
      const response = await rawPost(REGISTER_URL, { ...item, school: undefined }, school);
      const body = (await response.json()) as Result & { detail?: string };
      if (!response.ok) {
        setMessage({ tone: "error", text: body.detail ?? "The register could not be saved." });
        return;
      }
      const conflicts = body.conflicts.length
        ? ` ${body.conflicts.length} mark(s) were kept because someone recorded them later.`
        : "";
      setMessage({ tone: "success", text: `Register saved.${conflicts}` });
      client.invalidateQueries({ queryKey: ["register", arm, date] });
    } catch {
      enqueue(item);
      setPending(readQueue().length);
      setMessage({
        tone: "warning",
        text: "You're offline. The register is saved on this device and will be sent automatically.",
      });
    } finally {
      setSaving(false);
    }
  }

  const rows = sheet.data?.rows ?? [];
  const counts = STATUSES.map((s) => ({ ...s, n: rows.filter((r) => marks[r.student] === s.value).length }));

  return (
    <>
      <PageHeader title="Attendance" description="Tap a status for each pupil, then save. Works offline." />
      {!online && (
        <Alert tone="warning">You're offline. You can still take a register you've already opened.</Alert>
      )}
      {pending > 0 && (
        <div className="my-3">
          <Alert tone="info">
            {pending} register(s) waiting to be sent.{" "}
            {online && (
              <button type="button" className="font-medium underline" onClick={() => void sync()}>
                Send now
              </button>
            )}
          </Alert>
        </div>
      )}

      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_12rem]">
        <Field label="Class">
          <Select value={arm} onChange={(e) => setArm(e.target.value)}>
            {arms.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Date">
          <Input type="date" value={date} max={todayInAccra()} onChange={(e) => setDate(e.target.value)} />
        </Field>
      </div>

      {arms.data?.length === 0 && <Empty>You aren't assigned to any class yet.</Empty>}
      <ErrorText error={sheet.error} />
      {sheet.isPending && arm && online ? (
        <Loading />
      ) : rows.length ? (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
            <Button variant="secondary" onClick={() => markAll("present")}>
              Mark all present
            </Button>
            {counts.map((c) => (
              <span key={c.value} className="text-neutral-600 dark:text-neutral-400">
                {c.title}: <strong>{c.n}</strong>
              </span>
            ))}
          </div>
          <ul className="divide-y divide-neutral-100 rounded-xl border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
            {rows.map((r) => (
              <li key={r.student} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div>
                  <div className="font-medium">{r.name}</div>
                  <div className="font-mono text-xs text-neutral-500">{r.admission_number}</div>
                </div>
                <fieldset className="flex gap-1" aria-label={`Status for ${r.name}`}>
                  {STATUSES.map((s) => {
                    const active = marks[r.student] === s.value;
                    return (
                      <button
                        key={s.value}
                        type="button"
                        title={s.title}
                        aria-pressed={active}
                        onClick={() => setMarks((m) => ({ ...m, [r.student]: s.value }))}
                        className={`h-10 w-10 rounded-lg text-sm font-semibold ${
                          active
                            ? `${s.tone} text-white`
                            : "bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300"
                        }`}
                      >
                        {s.label}
                      </button>
                    );
                  })}
                </fieldset>
              </li>
            ))}
          </ul>
          {message && (
            <div className="mt-3">
              <Alert tone={message.tone}>{message.text}</Alert>
            </div>
          )}
          <div className="sticky bottom-0 mt-4 flex justify-end bg-gradient-to-t from-white py-3 dark:from-neutral-950">
            <Button onClick={() => void save()} busy={saving}>
              Save register
            </Button>
          </div>
        </>
      ) : (
        arm && online && !sheet.isPending && <Empty>No active pupils in this class.</Empty>
      )}
    </>
  );
}
