"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useState } from "react";
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
  Table,
  Td,
} from "@/components/ui";
import { api, type Paged, type Student } from "@/lib/api";
import { useArms, useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

type ImportReport = {
  rows: number;
  created: number;
  dry_run: boolean;
  errors: { row: number; column: string; message: string }[];
};

export default function StudentsPage() {
  const { can } = useSchool();
  const canManage = can(PERM.STUDENTS_MANAGE);
  // Class teachers add pupils straight into their own class; subject teachers can't add any.
  const ownClassOnly = !canManage && can(PERM.STUDENTS_ADD_OWN_CLASS);
  const formArms = useArms("form", ownClassOnly);
  const canAdd = canManage || (ownClassOnly && Boolean(formArms.data?.length));
  const [q, setQ] = useState("");
  const [arm, setArm] = useState("");
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const arms = useArms();

  const params = new URLSearchParams({ page_size: "200" });
  if (q) params.set("q", q);
  if (arm) params.set("arm", arm);
  const students = useQuery({
    queryKey: ["students", q, arm],
    queryFn: () => api.get<Paged<Student>>(`/api/v1/students?${params}`),
  });

  return (
    <>
      <PageHeader
        title="Students"
        description="Search by name or admission number."
        actions={
          canAdd && (
            <>
              {canManage && (
                <Button variant="secondary" onClick={() => setImporting(true)}>
                  Import CSV / Excel
                </Button>
              )}
              <Button onClick={() => setCreating(true)}>Add student</Button>
            </>
          )
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_14rem]">
        <Input placeholder="Search students…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={arm} onChange={(e) => setArm(e.target.value)} aria-label="Class">
          <option value="">All classes</option>
          {arms.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </Select>
      </div>

      <ErrorText error={students.error} />
      {students.isPending ? (
        <Loading />
      ) : students.data?.results.length ? (
        <Table head={["Admission no.", "Name", "Class", "Gender", "Status"]}>
          {students.data.results.map((s) => (
            <tr key={s.id}>
              <Td className="font-mono text-xs">{s.admission_number}</Td>
              <Td>
                <Link href={`/students/${s.id}`} className="font-medium hover:underline">
                  {s.last_name} {s.first_name} {s.middle_name}
                </Link>
              </Td>
              <Td>{s.arm_name ?? "—"}</Td>
              <Td className="capitalize">{s.gender}</Td>
              <Td>
                <Badge>{s.status}</Badge>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No students found.</Empty>
      )}

      <Modal open={creating} onClose={() => setCreating(false)} title="Add a student">
        <CreateStudent ownClassOnly={ownClassOnly} onDone={() => setCreating(false)} />
      </Modal>
      <Modal open={importing} onClose={() => setImporting(false)} title="Import students">
        <ImportStudents onDone={() => setImporting(false)} />
      </Modal>
    </>
  );
}

function CreateStudent({ ownClassOnly, onDone }: { ownClassOnly: boolean; onDone: () => void }) {
  const client = useQueryClient();
  const arms = useArms(ownClassOnly ? "form" : false);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post<Student>("/api/v1/students", body),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["students"] });
      onDone();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    create.mutate({ ...f, arm: f.arm || null });
  };
  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="First name">
        <Input name="first_name" required />
      </Field>
      <Field label="Last name">
        <Input name="last_name" required />
      </Field>
      <Field label="Other names">
        <Input name="middle_name" />
      </Field>
      <Field label="Date of birth">
        <Input name="date_of_birth" type="date" required />
      </Field>
      <Field label="Gender">
        <Select name="gender" required>
          <option value="female">Female</option>
          <option value="male">Male</option>
        </Select>
      </Field>
      <Field
        label="Class"
        hint={
          ownClassOnly
            ? "Pupils you add join your class straight away."
            : "They join this class straight away: its registers, score sheets and report cards."
        }
      >
        <Select
          name="arm"
          required
          defaultValue={ownClassOnly && arms.data?.length === 1 ? arms.data[0]?.id : ""}
        >
          <option value="" disabled>
            Choose a class
          </option>
          {arms.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Hometown">
        <Input name="hometown" />
      </Field>
      <Field label="Admission number" hint="Leave blank to generate one">
        <Input name="admission_number" />
      </Field>
      <div className="sm:col-span-2">
        <ErrorText error={create.error} />
      </div>
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button type="submit" busy={create.isPending}>
          Save student
        </Button>
      </div>
    </form>
  );
}

function ImportStudents({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const run = useMutation({
    mutationFn: async (dryRun: boolean) => {
      const form = new FormData();
      if (file) form.append("file", file);
      form.append("dry_run", dryRun ? "1" : "0");
      try {
        return await api.post<ImportReport>("/api/v1/students/import", form);
      } catch (error) {
        // A 400 still carries the row-by-row report.
        const body = (error as { body?: ImportReport }).body;
        if (body?.errors) return body;
        throw error;
      }
    },
    onSuccess: (data) => {
      setReport(data);
      if (data.created) client.invalidateQueries({ queryKey: ["students"] });
    },
  });

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-neutral-600 dark:text-neutral-400">
        Columns: <code>first_name, last_name, date_of_birth, gender, class</code> and optionally{" "}
        <code>
          middle_name, admission_number, guardian_name, guardian_phone, guardian_email, hometown, region
        </code>
        . Class is written like <code>JHS 1 A</code> or <code>Basic 4 A</code>. If any row has a problem,
        nothing is imported.
      </p>
      <Input type="file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <ErrorText error={run.error} />
      {report && report.errors.length > 0 && (
        <Alert tone="error">
          <p className="mb-1 font-medium">{report.errors.length} problem(s) found. Nothing was imported.</p>
          <ul className="max-h-48 list-disc overflow-auto pl-5">
            {report.errors.map((e, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: errors have no id.
              <li key={i}>
                Row {e.row}
                {e.column && ` (${e.column})`}: {e.message}
              </li>
            ))}
          </ul>
        </Alert>
      )}
      {report && !report.errors.length && report.dry_run && (
        <Alert tone="success">All {report.rows} rows look good. Click Import to save them.</Alert>
      )}
      {report && report.created > 0 && <Alert tone="success">{report.created} students imported.</Alert>}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" disabled={!file} busy={run.isPending} onClick={() => run.mutate(true)}>
          Check file
        </Button>
        {report?.created ? (
          <Button onClick={onDone}>Done</Button>
        ) : (
          <Button disabled={!file} busy={run.isPending} onClick={() => run.mutate(false)}>
            Import
          </Button>
        )}
      </div>
    </div>
  );
}
