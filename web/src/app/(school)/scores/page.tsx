"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Empty,
  ErrorText,
  Field,
  Loading,
  PageHeader,
  Select,
  Table,
  Td,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useArms, useCurrentTerm, useSchool, useSubjects } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Component = { id: number; name: string; code: string; max_score: string };
type Sheet = {
  components: Component[];
  rows: {
    student: string;
    admission_number: string;
    name: string;
    locked: boolean;
    scores: Record<string, string | null>;
  }[];
};

export default function ScoresPage() {
  const { can } = useSchool();
  const client = useQueryClient();
  const term = useCurrentTerm();
  const arms = useArms(!can(PERM.ASSESSMENTS_MANAGE));
  const [arm, setArm] = useState("");
  const subjects = useSubjects(arm || undefined);
  const [subject, setSubject] = useState("");
  const [draft, setDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!arm && arms.data?.[0]) setArm(arms.data[0].id);
  }, [arms.data, arm]);
  useEffect(() => {
    setSubject(subjects.data?.[0] ? String(subjects.data[0].id) : "");
  }, [subjects.data]);

  const ready = Boolean(arm && subject && term.data);
  const sheet = useQuery({
    queryKey: ["score-sheet", arm, subject, term.data?.id],
    queryFn: () =>
      api.get<Sheet>(`/api/v1/assessments/scores?arm=${arm}&subject=${subject}&term=${term.data?.id}`),
    enabled: ready,
  });
  // biome-ignore lint/correctness/useExhaustiveDependencies: clear unsaved edits whenever a fresh sheet loads.
  useEffect(() => setDraft({}), [sheet.data]);

  const cellKey = (student: string, component: number) => `${student}:${component}`;
  const cellValue = (student: string, c: Component) =>
    draft[cellKey(student, c.id)] ??
    sheet.data?.rows.find((r) => r.student === student)?.scores[String(c.id)] ??
    "";

  const invalid = useMemo(() => {
    const bad = new Set<string>();
    for (const [key, value] of Object.entries(draft)) {
      if (value === "") continue;
      const c = sheet.data?.components.find((x) => x.id === Number(key.split(":")[1]));
      const n = Number(value);
      if (!c || Number.isNaN(n) || n < 0 || n > Number(c.max_score)) bad.add(key);
    }
    return bad;
  }, [draft, sheet.data]);

  const save = useMutation({
    mutationFn: () =>
      api.post<{ changed: number; cleared: number }>("/api/v1/assessments/scores", {
        arm,
        subject: Number(subject),
        term: term.data?.id,
        entries: Object.entries(draft).map(([key, value]) => {
          const [student, component] = key.split(":");
          return { student, component: Number(component), score: value === "" ? null : value };
        }),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["score-sheet", arm, subject] }),
  });

  const total = (student: string) =>
    (sheet.data?.components ?? []).reduce((sum, c) => sum + (Number(cellValue(student, c)) || 0), 0);

  return (
    <>
      <PageHeader
        title="Score entry"
        description={
          term.data ? `${term.data.label}. Scores lock when results are published.` : "No current term."
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Field label="Class">
          <Select value={arm} onChange={(e) => setArm(e.target.value)}>
            {arms.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Subject">
          <Select value={subject} onChange={(e) => setSubject(e.target.value)}>
            {subjects.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {arm && subjects.data?.length === 0 && <Empty>No subjects are assigned to this class yet.</Empty>}
      <ErrorText error={sheet.error} />
      {sheet.isPending && ready ? (
        <Loading />
      ) : sheet.data?.rows.length ? (
        <>
          <Table
            head={[
              "Pupil",
              ...sheet.data.components.map((c) => `${c.name} (/${Number(c.max_score)})`),
              "Total",
            ]}
          >
            {sheet.data.rows.map((r) => (
              <tr key={r.student}>
                <Td>
                  <div className="font-medium">{r.name}</div>
                  <div className="font-mono text-xs text-neutral-500">{r.admission_number}</div>
                </Td>
                {sheet.data.components.map((c) => {
                  const key = cellKey(r.student, c.id);
                  return (
                    <Td key={c.id}>
                      <input
                        inputMode="decimal"
                        aria-label={`${c.name} for ${r.name}`}
                        disabled={r.locked}
                        value={cellValue(r.student, c)}
                        onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value.trim() }))}
                        className={`input w-20 text-right tabular-nums ${invalid.has(key) ? "border-red-600 ring-2 ring-red-200" : ""}`}
                      />
                    </Td>
                  );
                })}
                <Td className="font-semibold tabular-nums">{total(r.student).toFixed(2)}</Td>
              </tr>
            ))}
          </Table>
          <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
            {invalid.size > 0 && (
              <span className="text-sm text-red-700">Some scores are above the maximum.</span>
            )}
            {save.isSuccess && <Alert tone="success">Saved {save.data.changed} score(s).</Alert>}
            <ErrorText error={save.error} />
            <Button
              disabled={!Object.keys(draft).length || invalid.size > 0}
              busy={save.isPending}
              onClick={() => save.mutate()}
            >
              Save scores
            </Button>
          </div>
        </>
      ) : (
        ready && !sheet.isPending && <Empty>No active pupils in this class.</Empty>
      )}
    </>
  );
}
