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
  Loading,
  Modal,
  PageHeader,
  Select,
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { api, download, type ReportCard } from "@/lib/api";
import { useArms, useCurrentTerm, useSchool, useTerms } from "@/lib/hooks";
import { hasAny, isParentOnly } from "@/lib/roles";

export default function ResultsPage() {
  const { roles } = useSchool();
  const parent = isParentOnly(roles);
  const canPublish = hasAny(roles, ["owner", "principal", "admin"]);
  const client = useQueryClient();
  const terms = useTerms();
  const current = useCurrentTerm();
  const arms = useArms(!canPublish);
  const [term, setTerm] = useState("");
  const [arm, setArm] = useState("");
  const [open, setOpen] = useState<ReportCard | null>(null);

  useEffect(() => {
    if (!term && current.data) setTerm(String(current.data.id));
  }, [current.data, term]);
  useEffect(() => {
    if (!arm && arms.data?.[0] && !parent) setArm(arms.data[0].id);
  }, [arms.data, arm, parent]);

  const query = new URLSearchParams();
  if (term) query.set("term", term);
  if (arm && !parent) query.set("arm", arm);
  const cards = useQuery({
    queryKey: ["report-cards", term, parent ? "mine" : arm],
    queryFn: () => api.get<ReportCard[]>(`/api/v1/assessments/report-cards?${query}`),
    enabled: Boolean(term) && (parent || Boolean(arm)),
  });

  const act = useMutation({
    mutationFn: (kind: "compute" | "publish") =>
      api.post<Record<string, number>>(`/api/v1/assessments/results/${kind}`, { arm, term: Number(term) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["report-cards"] }),
  });

  const drafts = cards.data?.filter((c) => c.status === "draft").length ?? 0;

  return (
    <>
      <PageHeader
        title={parent ? "Report cards" : "Results"}
        description={
          parent
            ? "Published terminal reports for your children."
            : "Compute positions and publish report cards to parents."
        }
        actions={
          canPublish &&
          arm && (
            <>
              <Button
                variant="secondary"
                busy={act.isPending && act.variables === "compute"}
                onClick={() => act.mutate("compute")}
              >
                Compute results
              </Button>
              <Button
                disabled={!drafts}
                busy={act.isPending && act.variables === "publish"}
                onClick={() => act.mutate("publish")}
              >
                Publish {drafts ? `(${drafts})` : ""}
              </Button>
            </>
          )
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2">
        <Field label="Term">
          <Select value={term} onChange={(e) => setTerm(e.target.value)}>
            {terms.data?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
        {!parent && (
          <Field label="Class">
            <Select value={arm} onChange={(e) => setArm(e.target.value)}>
              {arms.data?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </Select>
          </Field>
        )}
      </div>

      <ErrorText error={act.error} />
      {act.isSuccess && (
        <div className="mb-3">
          <Alert tone="success">
            {act.variables === "publish"
              ? `Published ${act.data.published} report card(s). Parents have been notified.`
              : `Computed: ${act.data.created} new, ${act.data.updated} updated${act.data.skipped_published ? `, ${act.data.skipped_published} already published` : ""}.`}
          </Alert>
        </div>
      )}
      <ErrorText error={cards.error} />
      {cards.isPending && term ? (
        <Loading />
      ) : cards.data?.length ? (
        <Table head={["Pos.", "Pupil", "Average", "Aggregate", "Attendance", "Status", ""]}>
          {cards.data.map((c) => (
            <tr key={c.id}>
              <Td className="tabular-nums">{c.position_label || "—"}</Td>
              <Td>
                <div className="font-medium">{c.student_name}</div>
                <div className="text-xs text-neutral-500">{c.arm_label}</div>
              </Td>
              <Td className="tabular-nums">{c.average}%</Td>
              <Td>{c.aggregate ?? "—"}</Td>
              <Td>
                {c.days_present}/{c.days_open}
              </Td>
              <Td>
                <Badge>{c.status}</Badge>
              </Td>
              <Td className="whitespace-nowrap">
                <Button variant="ghost" onClick={() => setOpen(c)}>
                  View
                </Button>
                {c.has_pdf && (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      download(`/api/v1/assessments/report-cards/${c.id}/pdf`, `${c.admission_number}.pdf`)
                    }
                  >
                    PDF
                  </Button>
                )}
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        term &&
        !cards.isPending && (
          <Empty>
            {parent ? "No published report cards yet." : "No results computed for this class yet."}
          </Empty>
        )
      )}

      <Modal open={Boolean(open)} onClose={() => setOpen(null)} title={open?.student_name ?? ""}>
        {open && <CardDetail card={open} canComment={!parent} onSaved={() => setOpen(null)} />}
      </Modal>
    </>
  );
}

function CardDetail({
  card,
  canComment,
  onSaved,
}: {
  card: ReportCard;
  canComment: boolean;
  onSaved: () => void;
}) {
  const client = useQueryClient();
  const [teacher, setTeacher] = useState(card.form_teacher_comment);
  const [head, setHead] = useState(card.principal_comment);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, string> = {};
      if (teacher !== card.form_teacher_comment) body.form_teacher_comment = teacher;
      if (head !== card.principal_comment) body.principal_comment = head;
      return api.patch(`/api/v1/assessments/report-cards/${card.id}`, body);
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["report-cards"] });
      onSaved();
    },
  });
  const codes = Object.keys(card.lines[0]?.components ?? {});
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        {card.term_label} · {card.arm_label} · Average {card.average}% · {card.position_label}
        {card.aggregate !== null && ` · Aggregate ${card.aggregate}`}
      </p>
      <Table head={["Subject", ...codes, "Total", "Grade", "Pos."]}>
        {card.lines.map((l) => (
          <tr key={l.code}>
            <Td>{l.subject}</Td>
            {codes.map((code) => (
              <Td key={code} className="tabular-nums">
                {l.components[code] ?? "—"}
              </Td>
            ))}
            <Td className="tabular-nums font-medium">{l.total}</Td>
            <Td>
              {l.grade} <span className="text-xs text-neutral-500">{l.remark}</span>
            </Td>
            <Td>{l.position}</Td>
          </tr>
        ))}
      </Table>
      {canComment ? (
        <Card title="Comments">
          <div className="flex flex-col gap-3">
            <Field label="Class teacher">
              <Textarea
                value={teacher}
                onChange={(e) => setTeacher(e.target.value)}
                rows={2}
                maxLength={500}
              />
            </Field>
            <Field label="Head teacher">
              <Textarea value={head} onChange={(e) => setHead(e.target.value)} rows={2} maxLength={500} />
            </Field>
            <ErrorText error={save.error} />
            <div className="flex justify-end">
              <Button busy={save.isPending} onClick={() => save.mutate()}>
                Save comments
              </Button>
            </div>
          </div>
        </Card>
      ) : (
        <div className="text-sm">
          <p>
            <strong>Class teacher:</strong> {card.form_teacher_comment || "—"}
          </p>
          <p>
            <strong>Head teacher:</strong> {card.principal_comment || "—"}
          </p>
        </div>
      )}
    </div>
  );
}
