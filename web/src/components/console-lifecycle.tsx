"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
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
  Textarea,
} from "@/components/ui";
import { apiFetch, type Me, type PlatformSchool } from "@/lib/api";
import { cedis, formatDate, timeAgo } from "@/lib/format";

type Action = "suspend" | "reactivate" | "offboard";

const ACTION: Record<Action, { label: string; title: string; hint: string }> = {
  suspend: {
    label: "Suspend",
    title: "Suspend this school",
    hint: "Nobody at the school can sign in until it is reactivated. The proprietor is emailed the reason.",
  },
  reactivate: {
    label: "Reactivate",
    title: "Reactivate this school",
    hint: "Everyone at the school can sign in again.",
  },
  offboard: {
    label: "Close the school",
    title: "Close this school",
    hint: "The proprietor gets a full export now. The data stays locked for 90 days, then it is destroyed for good.",
  },
};

function useRoles() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }) });
  const roles = me.data?.platform_roles ?? [];
  return {
    superAdmin: roles.includes("super_admin"),
    money: roles.some((r) => r === "super_admin" || r === "billing"),
  };
}

/** Suspend, reactivate or close a school (Super Admin), with the reason and what happens next. */
export function LifecycleCard({ school }: { school: PlatformSchool }) {
  const client = useQueryClient();
  const { superAdmin } = useRoles();
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const run = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/platform/tenants/${school.slug}/lifecycle`, {
        method: "POST",
        school: false,
        body: { action, reason, confirm },
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["platform", "tenant", school.slug] });
      setAction(null);
    },
  });
  const l = school.lifecycle;
  const actions: Action[] =
    school.status === "active"
      ? ["suspend", "offboard"]
      : school.status === "suspended"
        ? ["reactivate", "offboard"]
        : school.status === "offboarded" && !l.purged_at
          ? ["reactivate"]
          : [];
  return (
    <Card title="Account status">
      {school.status === "suspended" && (
        <Alert tone="warning">
          Suspended {l.status_changed_at ? timeAgo(l.status_changed_at) : ""}
          {l.status_reason === "nonpayment" ? " for an unpaid invoice" : ""}
          {l.status_note ? `: ${l.status_note}` : "."}
          {l.status_reason === "nonpayment" && " It comes back by itself when the proprietor pays."}
        </Alert>
      )}
      {school.status === "offboarded" &&
        (l.purged_at ? (
          <Alert>Closed. The school's data was destroyed on {formatDate(l.purged_at)}.</Alert>
        ) : (
          <Alert tone="warning">
            Closed{l.status_note ? `: ${l.status_note}` : ""}. The data is destroyed on{" "}
            {formatDate(l.purge_after)} unless the school comes back before then.
          </Alert>
        ))}
      {school.status === "active" && (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Active. Everyone at the school can sign in.
        </p>
      )}
      {superAdmin && actions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {actions.map((a) => (
            <Button
              key={a}
              variant={a === "offboard" ? "danger" : "secondary"}
              onClick={() => {
                setReason("");
                setConfirm("");
                run.reset();
                setAction(a);
              }}
            >
              {ACTION[a].label}
            </Button>
          ))}
        </div>
      )}
      <Modal
        open={action !== null}
        onClose={() => setAction(null)}
        title={action ? ACTION[action].title : ""}
      >
        {action && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              run.mutate();
            }}
          >
            <p className="text-sm">{ACTION[action].hint}</p>
            <Field label="Reason" hint="Kept in the audit log.">
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                maxLength={300}
                required={action !== "reactivate"}
              />
            </Field>
            {action === "offboard" && (
              <Field label={`Type ${school.slug} to confirm`}>
                <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
              </Field>
            )}
            <ErrorText error={run.error} />
            <div className="flex justify-end">
              <Button
                type="submit"
                variant={action === "offboard" ? "danger" : "primary"}
                busy={run.isPending}
                disabled={action === "offboard" && confirm !== school.slug}
              >
                {ACTION[action].label}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </Card>
  );
}

/** What the school owes Nex Edu and its SMS; billing staff can add SMS free of charge. */
export function SchoolBillingCard({ school }: { school: PlatformSchool }) {
  const client = useQueryClient();
  const { superAdmin } = useRoles();
  const [gift, setGift] = useState(false);
  const add = useMutation({
    mutationFn: (body: { sms: number; reason: string }) =>
      apiFetch(`/api/v1/platform/tenants/${school.slug}/sms`, { method: "POST", school: false, body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["platform", "tenant", school.slug] });
      setGift(false);
    },
  });
  const b = school.billing;
  return (
    <Card title="Invoices and SMS">
      <dl className="grid gap-2 text-sm">
        <Row label="Unpaid">
          {b.unpaid_invoices
            ? `${cedis(b.unpaid_pesewas)} (${b.unpaid_invoices} invoice${b.unpaid_invoices === 1 ? "" : "s"})`
            : "Nothing"}
        </Row>
        {b.oldest_due_on && <Row label="Oldest due">{formatDate(b.oldest_due_on)}</Row>}
        <Row label="SMS each month">{b.sms.monthly.toLocaleString("en-GB")}</Row>
        <Row label="Bought SMS left">{b.sms.bought.toLocaleString("en-GB")}</Row>
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Link
          href={`/platform/billing/invoices?school=${school.slug}`}
          className="text-sm text-link underline hover:text-link-hover"
        >
          See invoices
        </Link>
        {superAdmin && (
          <Button variant="secondary" onClick={() => setGift(true)}>
            Add SMS
          </Button>
        )}
      </div>
      <Modal open={gift} onClose={() => setGift(false)} title="Add SMS free of charge">
        {gift && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              add.mutate({ sms: Number(f.get("sms")), reason: String(f.get("reason") ?? "") });
            }}
          >
            <Field label="How many SMS">
              <Input name="sms" type="number" min={1} max={100000} required />
            </Field>
            <Field label="Reason" hint="Kept in the audit log.">
              <Input name="reason" required maxLength={300} />
            </Field>
            <ErrorText error={add.error} />
            <div className="flex justify-end">
              <Button type="submit" busy={add.isPending}>
                Add SMS
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </Card>
  );
}

type Configuration = {
  grant: { reason: string; expires_at: string; granted_by: string };
  profile: { name: string; address: string; phone: string; has_logo: boolean; terms_accepted: boolean };
  year: string;
  term: string;
  classes: { name: string; pupils: number }[];
  subjects: string[];
  modules: { name: string; active: boolean }[];
  staff: { name: string; email: string; roles: string[]; last_sign_in: string | null }[];
  setup: { done: number; total: number; left: string[] };
};

/** The school's set-up, only while the proprietor allows support access. Every look is recorded. */
export function SupportAccessCard({ school }: { school: PlatformSchool }) {
  const [look, setLook] = useState(false);
  const open = school.billing.support_open_until;
  const config = useQuery({
    queryKey: ["platform", "support-look", school.slug],
    queryFn: () =>
      apiFetch<Configuration>(`/api/v1/platform/tenants/${school.slug}/support?look=1`, { school: false }),
    enabled: look,
    staleTime: Number.POSITIVE_INFINITY,
  });
  return (
    <Card title="Support access">
      {open ? (
        <>
          <p className="text-sm">
            The proprietor allows support to see the school's set-up until {formatDate(open)}. Pupils' records
            are never shown. Each look is recorded and the proprietor sees it.
          </p>
          {!look && (
            <div className="mt-3">
              <Button variant="secondary" onClick={() => setLook(true)}>
                Look at the set-up
              </Button>
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Closed. The proprietor can open it for up to 7 days from the school's billing page.
        </p>
      )}
      {look &&
        (config.isPending ? (
          <Loading />
        ) : config.error ? (
          <ErrorText error={config.error} />
        ) : (
          config.data && <SetUp c={config.data} />
        ))}
    </Card>
  );
}

function SetUp({ c }: { c: Configuration }) {
  return (
    <div className="mt-4 flex flex-col gap-4 text-sm">
      <p className="text-neutral-600 dark:text-neutral-300">
        Asked for: “{c.grant.reason}” by {c.grant.granted_by}.
      </p>
      <dl className="grid gap-2">
        <Row label="Year and term">{[c.year, c.term].filter(Boolean).join(", ") || "Not set"}</Row>
        <Row label="Address and phone">
          {[c.profile.address, c.profile.phone].filter(Boolean).join(" · ") || "—"}
        </Row>
        <Row label="Logo">{c.profile.has_logo ? "Uploaded" : "None"}</Row>
        <Row label="Set-up">
          {c.setup.done} of {c.setup.total} steps
        </Row>
      </dl>
      {c.setup.left.length > 0 && <p>Still to do: {c.setup.left.join(" · ")}</p>}
      <section aria-label="Classes">
        <h3 className="mb-1 font-medium">Classes</h3>
        {c.classes.length ? (
          <ul className="grid gap-1 sm:grid-cols-2">
            {c.classes.map((k) => (
              <li key={k.name}>
                {k.name} <span className="text-neutral-500">({k.pupils} pupils)</span>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No classes.</Empty>
        )}
      </section>
      <section aria-label="Staff accounts">
        <h3 className="mb-1 font-medium">Staff accounts</h3>
        <ul className="flex flex-col gap-1">
          {c.staff.map((p) => (
            <li key={p.email}>
              {p.name}{" "}
              <span className="text-neutral-500">
                · {p.roles.join(", ")} · last sign-in {timeAgo(p.last_sign_in)}
              </span>
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="Modules">
        <h3 className="mb-1 font-medium">Modules</h3>
        <div className="flex flex-wrap gap-1">
          {c.modules.map((m) => (
            <Badge key={m.name} tone={m.active ? "green" : "grey"}>
              {m.name}
            </Badge>
          ))}
        </div>
      </section>
      <p>Subjects: {c.subjects.join(", ") || "none"}</p>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-neutral-500">{label}</dt>
      <dd className="min-w-0 text-right wrap-break-word">{children}</dd>
    </div>
  );
}
