"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import {
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
  Stat,
  Table,
  Td,
} from "@/components/ui";
import { api, download, type Guardian, type Invoice, type ReportCard, type Student } from "@/lib/api";
import { cedis, formatDate } from "@/lib/format";
import { useArms, useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type Attendance = {
  summary: { present: number; absent: number; late: number; excused: number; days_open: number } | null;
  records: { id: number; date: string; status: string; note: string }[];
};

export default function StudentPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSchool();
  const [addingGuardian, setAddingGuardian] = useState(false);
  const student = useQuery({
    queryKey: ["student", id],
    queryFn: () => api.get<Student>(`/api/v1/students/${id}`),
  });
  // Class teachers add guardians for pupils in their own class only.
  const ownClassOnly = !can(PERM.STUDENTS_MANAGE) && can(PERM.STUDENTS_ADD_OWN_CLASS);
  const formArms = useArms("form", ownClassOnly);
  const canAddGuardian =
    can(PERM.STUDENTS_MANAGE) ||
    (ownClassOnly && Boolean(formArms.data?.some((a) => a.id === student.data?.arm)));
  const guardians = useQuery({
    queryKey: ["guardians", id],
    queryFn: () => api.get<Guardian[]>(`/api/v1/students/${id}/guardians`),
  });
  const attendance = useQuery({
    queryKey: ["attendance", id],
    queryFn: () => api.get<Attendance>(`/api/v1/students/${id}/attendance`),
    retry: false,
  });
  const reports = useQuery({
    queryKey: ["report-cards", "student", id],
    queryFn: () => api.get<ReportCard[]>(`/api/v1/assessments/report-cards?student=${id}`),
    retry: false,
  });
  const invoices = useQuery({
    queryKey: ["invoices", "student", id],
    queryFn: () => api.get<Invoice[]>(`/api/v1/finance/invoices?student=${id}`),
    retry: false,
  });

  if (student.isPending) return <Loading />;
  if (student.error) return <ErrorText error={student.error} />;
  const s = student.data;
  const summary = attendance.data?.summary;

  return (
    <>
      <PageHeader
        title={`${s.first_name} ${s.middle_name} ${s.last_name}`.replace(/\s+/g, " ")}
        description={
          <>
            {s.admission_number} · {s.arm_name ?? "No class"} · <Badge>{s.status}</Badge>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat
          label="Attendance this term"
          value={summary ? `${summary.present}/${summary.days_open}` : "—"}
          hint={summary ? `${summary.absent} absent, ${summary.late} late` : undefined}
        />
        <Stat
          label="Latest average"
          value={reports.data?.[0] ? `${reports.data[0].average}%` : "—"}
          hint={reports.data?.[0]?.position_label}
        />
        <Stat
          label="Fees outstanding"
          value={invoices.data ? cedis(invoices.data.reduce((t, i) => t + i.balance_pesewas, 0)) : "—"}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card title="Details">
          <dl className="grid grid-cols-[9rem_1fr] gap-y-2 text-sm">
            <dt className="text-neutral-500">Date of birth</dt>
            <dd>{formatDate(s.date_of_birth)}</dd>
            <dt className="text-neutral-500">Gender</dt>
            <dd className="capitalize">{s.gender}</dd>
            <dt className="text-neutral-500">Hometown</dt>
            <dd>{s.hometown || "—"}</dd>
            <dt className="text-neutral-500">Admitted</dt>
            <dd>{formatDate(s.admitted_on)}</dd>
            {s.medical_notes !== undefined && (
              <>
                <dt className="text-neutral-500">Health notes</dt>
                <dd>{s.medical_notes || "—"}</dd>
                <dt className="text-neutral-500">Ghana Card</dt>
                <dd>{s.national_id || "—"}</dd>
              </>
            )}
          </dl>
        </Card>

        <Card
          title="Parents and guardians"
          actions={
            canAddGuardian && (
              <Button variant="secondary" onClick={() => setAddingGuardian(true)}>
                Add
              </Button>
            )
          }
        >
          {guardians.data?.length ? (
            <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
              {guardians.data.map((g) => (
                <li key={g.id} className="py-2">
                  <div className="font-medium">
                    {g.full_name || "Guardian"} <span className="text-neutral-500">({g.relationship})</span>
                    {g.is_primary && <Badge tone="blue">primary</Badge>}
                  </div>
                  <div className="text-neutral-600 dark:text-neutral-400">
                    {[g.phone, g.email].filter(Boolean).join(" · ")}
                    {g.guardian_user_id && " · has a login"}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No guardians recorded.</Empty>
          )}
        </Card>

        <Card title="Report cards">
          {reports.data?.length ? (
            <Table head={["Term", "Average", "Position", "Aggregate", ""]}>
              {reports.data.map((r) => (
                <tr key={r.id}>
                  <Td>{r.term_label}</Td>
                  <Td>{r.average}%</Td>
                  <Td>{r.position_label || "—"}</Td>
                  <Td>{r.aggregate ?? "—"}</Td>
                  <Td>
                    {r.has_pdf ? (
                      <Button
                        variant="ghost"
                        onClick={() =>
                          download(
                            `/api/v1/assessments/report-cards/${r.id}/pdf`,
                            `${r.admission_number}.pdf`,
                          )
                        }
                      >
                        PDF
                      </Button>
                    ) : (
                      <Badge>{r.status}</Badge>
                    )}
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No results yet.</Empty>
          )}
        </Card>

        <Card title="Fees">
          {invoices.data?.length ? (
            <Table head={["Invoice", "Term", "Total", "Balance", "Status"]}>
              {invoices.data.map((i) => (
                <tr key={i.id}>
                  <Td className="font-mono text-xs">
                    <Link href={`/fees?invoice=${i.id}`} className="hover:underline">
                      {i.number}
                    </Link>
                  </Td>
                  <Td>{i.term_label}</Td>
                  <Td>{cedis(i.total_pesewas)}</Td>
                  <Td>{cedis(i.balance_pesewas)}</Td>
                  <Td>
                    <Badge>{i.status}</Badge>
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No invoices.</Empty>
          )}
        </Card>
      </div>

      <Modal open={addingGuardian} onClose={() => setAddingGuardian(false)} title="Add a guardian">
        <AddGuardian studentId={id} onDone={() => setAddingGuardian(false)} />
      </Modal>
    </>
  );
}

function AddGuardian({ studentId, onDone }: { studentId: string; onDone: () => void }) {
  const client = useQueryClient();
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post(`/api/v1/students/${studentId}/guardians`, body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["guardians", studentId] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    add.mutate({ ...f, is_primary: f.is_primary === "on" });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Full name">
        <Input name="full_name" required />
      </Field>
      <Field label="Mobile number" hint="Ghanaian number, e.g. 024 412 3456">
        <Input name="phone" inputMode="tel" />
      </Field>
      <Field label="Email (optional)">
        <Input name="email" type="email" />
      </Field>
      <Field label="Relationship">
        <Input name="relationship" defaultValue="parent" />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="is_primary" /> Primary contact
      </label>
      <ErrorText error={add.error} />
      <div className="flex justify-end">
        <Button type="submit" busy={add.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}
