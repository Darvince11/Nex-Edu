"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, type ReactNode, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  ErrorText,
  Field,
  Loading,
  Modal,
  PageHeader,
  Textarea,
} from "@/components/ui";
import { ApiError, apiFetch, type Me, type PlatformRegistration } from "@/lib/api";
import { SCHOOL_DOMAIN } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { REGISTRATION_STATUSES } from "@/lib/registration";

type Decision = "approve" | "reject";

export default function RegistrationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [deciding, setDeciding] = useState<Decision | null>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }) });
  const registration = useQuery({
    queryKey: ["platform", "registration", id],
    queryFn: () => apiFetch<PlatformRegistration>(`/api/v1/platform/registrations/${id}`, { school: false }),
    // Set-up runs in the background after approval; check until it finishes.
    refetchInterval: (query) => (query.state.data?.status === "provisioning" ? 2000 : false),
  });

  if (registration.isPending) return <Loading />;
  if (registration.error) return <ErrorText error={registration.error} />;
  const r = registration.data;
  const status = REGISTRATION_STATUSES.find((s) => s.value === r.status);
  const canDecide = me.data?.platform_roles.includes("super_admin") && r.status === "pending";
  const ownApplication = me.data?.email === r.owner_email;

  function done(updated: PlatformRegistration) {
    queryClient.setQueryData(["platform", "registration", id], updated);
    void queryClient.invalidateQueries({ queryKey: ["platform", "registrations"] });
    setDeciding(null);
  }

  return (
    <>
      <Link
        href="/platform/registrations"
        className="mb-4 inline-block text-sm text-link hover:text-link-hover"
      >
        ← All registrations
      </Link>
      <PageHeader
        title={r.school_name}
        description={
          <span className="font-mono">
            {r.slug}.{SCHOOL_DOMAIN}
          </span>
        }
        actions={
          canDecide && !ownApplication ? (
            <>
              <Button variant="secondary" onClick={() => setDeciding("reject")}>
                Reject
              </Button>
              <Button onClick={() => setDeciding("approve")}>Approve and create school</Button>
            </>
          ) : undefined
        }
      />

      <div className="flex flex-col gap-4">
        {r.possible_duplicate && r.status === "pending" && (
          <Alert tone="warning">
            A school with this name is already on Nex Edu or waiting for review. Check it isn't the same
            school before approving.{" "}
            <Link href="/platform/schools" className="font-medium underline">
              See all schools
            </Link>
          </Alert>
        )}
        {r.status === "pending" && me.data && !me.data.platform_roles.includes("super_admin") && (
          <Alert tone="info">
            You can review this registration, but only a super admin can approve or reject it.
          </Alert>
        )}
        {ownApplication && r.status === "pending" && (
          <Alert tone="info">This is your own registration. Another super admin has to review it.</Alert>
        )}

        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="School">
            <Details
              rows={[
                [
                  "Status",
                  status ? (
                    <Badge key="status" tone={status.tone}>
                      {status.label}
                    </Badge>
                  ) : (
                    r.status
                  ),
                ],
                ["Classes", r.school_type_label],
                ["Location", `${r.town}, ${r.region_label} Region`],
                [
                  "Phone",
                  <a key="phone" href={`tel:${r.phone}`} className="text-link hover:text-link-hover">
                    {r.phone}
                  </a>,
                ],
                ["Pupils (about)", r.expected_pupils.toLocaleString("en-GB")],
                ["Submitted", formatDate(r.created_at)],
              ]}
            />
          </Card>
          <Card title="Applicant">
            <Details
              rows={[
                ["Name", r.owner_name || "—"],
                ["Email", r.owner_email],
                ["Account created", formatDate(r.owner_joined)],
              ]}
            />
            <p className="mt-3 text-xs text-neutral-500">
              Before approving: call the school phone number and confirm this person runs the school.
            </p>
          </Card>
        </div>

        {r.status === "provisioning" && (
          <Alert tone="info">
            Setting up the school's database. This usually takes under a minute, and you can leave this page;
            the owner is emailed when it's ready.
          </Alert>
        )}
        {r.status === "failed" && (
          <Alert tone="error">
            Setting up this school failed. No one was given access, and the half-made database was removed.
            The cause is under System settings → Problems; fix it, then try again.
            {me.data?.platform_roles.includes("super_admin") && <RetrySetup id={r.id} onDone={done} />}
          </Alert>
        )}
        {r.status !== "pending" && (
          <Card title="Decision">
            <Details
              rows={[
                ["Outcome", status?.label ?? r.status],
                ["Reviewed by", r.reviewed_by_email || "—"],
                ["Reviewed", r.reviewed_at ? formatDate(r.reviewed_at) : "—"],
                ["Note", r.review_note || "—"],
                ...(r.school_slug
                  ? ([["School", `${r.school_slug}.${SCHOOL_DOMAIN}`]] as [string, ReactNode][])
                  : []),
              ]}
            />
          </Card>
        )}
      </div>

      <Modal
        open={deciding !== null}
        onClose={() => setDeciding(null)}
        title={deciding === "approve" ? `Approve ${r.school_name}?` : `Reject ${r.school_name}?`}
      >
        {deciding && (
          <DecisionForm
            registration={r}
            decision={deciding}
            onDone={done}
            onCancel={() => setDeciding(null)}
          />
        )}
      </Modal>
    </>
  );
}

function Details({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-4 gap-y-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-neutral-500">{label}</dt>
          <dd className="min-w-0 wrap-break-word">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function DecisionForm({
  registration,
  decision,
  onDone,
  onCancel,
}: {
  registration: PlatformRegistration;
  decision: Decision;
  onDone: (r: PlatformRegistration) => void;
  onCancel: () => void;
}) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<string>();
  const submit = useMutation({
    mutationFn: () =>
      apiFetch<PlatformRegistration>(`/api/v1/platform/registrations/${registration.id}/${decision}`, {
        method: "POST",
        school: false,
        body: { note },
      }),
    onSuccess: onDone,
    onError: (e) => setError(e instanceof ApiError ? e.message : "Something went wrong. Try again."),
  });

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (decision === "reject" && !note.trim()) {
      setError("Give a reason. The applicant will see it.");
      return;
    }
    setError(undefined);
    submit.mutate();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {decision === "approve" ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          This creates the school's database at{" "}
          <span className="font-mono">
            {registration.slug}.{SCHOOL_DOMAIN}
          </span>{" "}
          and makes {registration.owner_email} its owner. They'll get an email and must set up a second step
          before seeing records.
        </p>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          No school is created. {registration.owner_email} gets an email with your reason and can apply again.
        </p>
      )}
      <Field
        label={
          decision === "approve" ? "Note (optional, for the audit log)" : "Reason (sent to the applicant)"
        }
      >
        <Textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} rows={3} />
      </Field>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant={decision === "approve" ? "primary" : "danger"} busy={submit.isPending}>
          {decision === "approve" ? "Approve and create school" : "Reject"}
        </Button>
      </div>
    </form>
  );
}

function RetrySetup({ id, onDone }: { id: string; onDone: (r: PlatformRegistration) => void }) {
  const retry = useMutation({
    mutationFn: () =>
      apiFetch<PlatformRegistration>(`/api/v1/platform/registrations/${id}/retry`, {
        method: "POST",
        school: false,
      }),
    onSuccess: onDone,
  });
  return (
    <span className="mt-2 flex flex-wrap items-center gap-2">
      <Button variant="secondary" busy={retry.isPending} onClick={() => retry.mutate()}>
        Try set-up again
      </Button>
      <ErrorText error={retry.error} />
    </span>
  );
}
