"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApplicationForm } from "@/components/application-form";
import {
  Alert,
  Badge,
  Button,
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
import { type Application, type Arm, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useArms, useSchool } from "@/lib/hooks";

const NEXT_STEPS: Record<string, { status: string; label: string; variant?: "secondary" | "danger" }[]> = {
  submitted: [
    { status: "under_review", label: "Start review", variant: "secondary" },
    { status: "offered", label: "Offer a place" },
    { status: "rejected", label: "Decline", variant: "danger" },
  ],
  under_review: [
    { status: "offered", label: "Offer a place" },
    { status: "rejected", label: "Decline", variant: "danger" },
  ],
  offered: [{ status: "withdrawn", label: "Mark withdrawn", variant: "secondary" }],
};

export default function AdmissionsPage() {
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<Application | null>(null);
  const [creating, setCreating] = useState(false);
  const { slug } = useSchool();
  const apps = useQuery({
    queryKey: ["applications", status],
    queryFn: () =>
      api.get<Application[]>(`/api/v1/admissions/applications${status ? `?status=${status}` : ""}`),
  });

  return (
    <>
      <PageHeader
        title="Admissions"
        description={
          <>
            Parents can apply online at <code>/apply?school={slug}</code> on your school's address.
          </>
        }
        actions={<Button onClick={() => setCreating(true)}>New application</Button>}
      />
      <div className="mb-4 w-56">
        <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All applications</option>
          {["submitted", "under_review", "offered", "enrolled", "rejected", "withdrawn"].map((s) => (
            <option key={s} value={s}>
              {s.replace("_", " ")}
            </option>
          ))}
        </Select>
      </div>
      <ErrorText error={apps.error} />
      {apps.isPending ? (
        <Loading />
      ) : apps.data?.length ? (
        <Table head={["Reference", "Applicant", "Class", "Guardian", "Received", "Status"]}>
          {apps.data.map((a) => (
            <tr
              key={a.id}
              onClick={() => setOpen(a)}
              className="cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-900"
            >
              <Td className="font-mono text-xs">{a.reference}</Td>
              <Td className="font-medium">
                {a.first_name} {a.last_name}
              </Td>
              <Td>{a.desired_level_name}</Td>
              <Td>
                {a.guardian_name}
                <div className="text-xs text-neutral-500">{a.guardian_phone}</div>
              </Td>
              <Td>
                {formatDate(a.created_at)} <span className="text-xs text-neutral-500">({a.source})</span>
              </Td>
              <Td>
                <Badge>{a.status}</Badge>
              </Td>
            </tr>
          ))}
        </Table>
      ) : (
        <Empty>No applications yet.</Empty>
      )}
      <Modal
        open={Boolean(open)}
        onClose={() => setOpen(null)}
        title={open ? `${open.first_name} ${open.last_name}` : ""}
      >
        {open && <Review application={open} onDone={() => setOpen(null)} />}
      </Modal>
      <Modal open={creating} onClose={() => setCreating(false)} title="New application">
        <ApplicationForm onDone={() => setCreating(false)} />
      </Modal>
    </>
  );
}

function Review({ application: a, onDone }: { application: Application; onDone: () => void }) {
  const client = useQueryClient();
  const arms = useArms();
  const [notes, setNotes] = useState(a.review_notes);
  const levelArms = (arms.data ?? []).filter((arm: Arm) => arm.level === a.desired_level);
  const [arm, setArm] = useState("");
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["applications"] });
    client.invalidateQueries({ queryKey: ["students"] });
  };
  const change = useMutation({
    mutationFn: (status: string) =>
      api.post(`/api/v1/admissions/applications/${a.id}/change_status`, { status, notes }),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  const enrol = useMutation({
    mutationFn: () =>
      api.post(`/api/v1/admissions/applications/${a.id}/enrol`, {
        arm: arm || levelArms[0]?.id,
        invite_guardian: true,
      }),
    onSuccess: () => {
      refresh();
      onDone();
    },
  });
  return (
    <div className="flex flex-col gap-3 text-sm">
      <dl className="grid grid-cols-[9rem_1fr] gap-y-1">
        <dt className="text-neutral-500">Reference</dt>
        <dd className="font-mono">{a.reference}</dd>
        <dt className="text-neutral-500">Class</dt>
        <dd>{a.desired_level_name}</dd>
        <dt className="text-neutral-500">Date of birth</dt>
        <dd>{formatDate(a.date_of_birth)}</dd>
        <dt className="text-neutral-500">Previous school</dt>
        <dd>{a.previous_school || "—"}</dd>
        <dt className="text-neutral-500">Guardian</dt>
        <dd>
          {a.guardian_name} · {a.guardian_phone} {a.guardian_email && `· ${a.guardian_email}`}
        </dd>
      </dl>
      <Field label="Review notes">
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
      </Field>
      {a.status === "offered" && (
        <Alert tone="info">
          Enrolling creates the pupil record
          {a.guardian_email
            ? " and emails the guardian an invitation to Nex Edu."
            : ". Add a guardian email to send a login invite."}
          <div className="mt-2 flex items-end gap-2">
            <Select value={arm} onChange={(e) => setArm(e.target.value)} aria-label="Class arm">
              {levelArms.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.label}
                </option>
              ))}
            </Select>
            <Button busy={enrol.isPending} onClick={() => enrol.mutate()}>
              Enrol
            </Button>
          </div>
        </Alert>
      )}
      <ErrorText error={change.error ?? enrol.error} />
      <div className="flex flex-wrap justify-end gap-2">
        {(NEXT_STEPS[a.status] ?? []).map((step) => (
          <Button
            key={step.status}
            variant={step.variant}
            busy={change.isPending && change.variables === step.status}
            onClick={() => change.mutate(step.status)}
          >
            {step.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
