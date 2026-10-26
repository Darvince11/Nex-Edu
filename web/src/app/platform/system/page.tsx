"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  Loading,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Textarea,
} from "@/components/ui";
import { apiFetch, type Me, type Problem, type SecurityActivity, type SystemStatus } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { AUDIT_ACTIONS } from "@/lib/platform";

type Tab = "problems" | "security" | "updates" | "vulnerabilities";
const TABS: [Tab, string][] = [
  ["problems", "Problems"],
  ["security", "Sign-in and security"],
  ["updates", "Updates and health"],
  ["vulnerabilities", "Vulnerabilities"],
];
const STATUS_LABEL: Record<Problem["status"], string> = {
  new: "New",
  investigating: "Investigating",
  fixed: "Fixed",
  ignored: "Ignored",
};

/**
 * Everything that can go wrong, in one place, so Nex Edu staff fix it before
 * schools notice: errors and failed jobs, suspicious sign-ins and password
 * resets, schools whose database needs updating, and known vulnerabilities.
 */
export default function SystemPage() {
  const [tab, setTab] = useState<Tab>("problems");
  return (
    <>
      <PageHeader
        title="System settings"
        description="Errors, failed jobs, sign-in activity, updates and security advisories across Nex Edu."
      />
      <div
        role="tablist"
        aria-label="System"
        className="mb-5 flex flex-wrap gap-1 border-b border-neutral-200 dark:border-neutral-800"
      >
        {TABS.map(([key, label]) => (
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
      <div role="tabpanel" aria-label={TABS.find(([k]) => k === tab)?.[1]}>
        {tab === "problems" && <Problems />}
        {tab === "security" && <Security />}
        {tab === "updates" && <Updates />}
        {tab === "vulnerabilities" && <Vulnerabilities />}
      </div>
    </>
  );
}

// --- Problems ---------------------------------------------------------------------------

function Problems() {
  const [status, setStatus] = useState("open");
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const params = new URLSearchParams({ status });
  if (kind) params.set("kind", kind);
  const list = useQuery({
    queryKey: ["platform", "problems", status, kind],
    queryFn: () =>
      apiFetch<{ open: number; critical_open: number; last_24h: number; problems: Problem[] }>(
        `/api/v1/platform/system/problems?${params}`,
        { school: false },
      ),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });

  if (list.isPending) return <Loading />;
  if (list.error) return <ErrorText error={list.error} />;
  const d = list.data;
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Open problems" value={d.open} />
        <Stat
          label="Critical and open"
          value={d.critical_open}
          hint="Server errors, failed jobs, health checks"
        />
        <Stat label="Seen in the last 24 hours" value={d.last_24h} />
      </div>
      <div className="mt-4 mb-4 flex flex-wrap gap-3">
        <div className="w-48">
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="open">Open (new or investigating)</option>
              <option value="fixed">Fixed</option>
              <option value="ignored">Ignored</option>
              <option value="all">Everything</option>
            </Select>
          </Field>
        </div>
        <div className="w-56">
          <Field label="Kind">
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">All kinds</option>
              <option value="server">Server errors</option>
              <option value="job">Failed background jobs</option>
              <option value="browser">Errors on people's screens</option>
              <option value="slow">Slow pages</option>
              <option value="health">Failed health checks</option>
            </Select>
          </Field>
        </div>
      </div>
      {!d.problems.length ? (
        <Empty>{status === "open" ? "Nothing is broken right now." : "No problems here."}</Empty>
      ) : (
        <ul className="grid gap-2">
          {d.problems.map((p) => (
            <li
              key={p.id}
              className="rounded-card border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900"
            >
              <button
                type="button"
                aria-expanded={open === p.id}
                onClick={() => setOpen(open === p.id ? null : p.id)}
                className="flex w-full flex-wrap items-start justify-between gap-3 p-3 text-left"
              >
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge tone={p.severity === "critical" ? "red" : "amber"}>
                      {p.severity === "critical" ? "Critical" : "Warning"}
                    </Badge>
                    <span className="text-xs text-neutral-500">{p.kind_label}</span>
                  </span>
                  <span className="mt-1 block font-medium wrap-break-word">{p.title}</span>
                  <span className="block text-xs text-neutral-500">
                    {p.location || p.last_path}
                    {p.schools.length
                      ? ` · ${p.schools.length} school${p.schools.length === 1 ? "" : "s"}`
                      : ""}
                  </span>
                </span>
                <span className="shrink-0 text-right text-xs text-neutral-500">
                  <span className="block font-medium text-neutral-800 tabular-nums dark:text-neutral-100">
                    {p.count.toLocaleString("en-GB")}×
                  </span>
                  last {timeAgo(p.last_seen)}
                  <span className="mt-1 block">
                    <Badge tone={p.status === "fixed" ? "green" : p.status === "new" ? "blue" : "grey"}>
                      {STATUS_LABEL[p.status]}
                    </Badge>
                  </span>
                </span>
              </button>
              {open === p.id && <ProblemDetail problem={p} />}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function ProblemDetail({ problem }: { problem: Problem }) {
  const client = useQueryClient();
  const [note, setNote] = useState(problem.note);
  const update = useMutation({
    mutationFn: (body: Partial<Problem>) =>
      apiFetch<Problem>(`/api/v1/platform/system/problems/${problem.id}`, {
        method: "PATCH",
        school: false,
        body,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["platform", "problems"] }),
  });
  return (
    <div className="border-t border-neutral-200 p-3 text-sm dark:border-neutral-800">
      <dl className="grid gap-1 text-xs sm:grid-cols-2">
        <div>
          <dt className="inline text-neutral-500">First seen: </dt>
          <dd className="inline">{formatDate(problem.first_seen)}</dd>
        </div>
        <div>
          <dt className="inline text-neutral-500">Page: </dt>
          <dd className="inline font-mono">{problem.last_path || "—"}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="inline text-neutral-500">Schools affected: </dt>
          <dd className="inline">
            {problem.schools.length
              ? problem.schools.map((s, i) => (
                  <span key={s}>
                    {i > 0 && ", "}
                    <Link href={`/platform/schools/${s}`} className="text-link underline">
                      {s}
                    </Link>
                  </span>
                ))
              : "None recorded"}
          </dd>
        </div>
      </dl>
      {problem.detail && (
        <pre className="mt-3 max-h-64 overflow-auto rounded-control bg-neutral-50 p-2 text-xs whitespace-pre-wrap dark:bg-neutral-950">
          {problem.detail}
        </pre>
      )}
      <p className="mt-1 text-xs text-neutral-500">
        Emails, phone numbers and secrets are removed before saving.
      </p>
      <div className="mt-3">
        <Field label="Notes for the team">
          <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
        {problem.updated_by_email && (
          <span className="mr-auto text-xs text-neutral-500">Last updated by {problem.updated_by_email}</span>
        )}
        <ErrorText error={update.error} />
        {note !== problem.note && (
          <Button variant="secondary" busy={update.isPending} onClick={() => update.mutate({ note })}>
            Save note
          </Button>
        )}
        {problem.status !== "investigating" && (
          <Button variant="secondary" onClick={() => update.mutate({ status: "investigating", note })}>
            Investigating
          </Button>
        )}
        {problem.status !== "ignored" && (
          <Button variant="ghost" onClick={() => update.mutate({ status: "ignored", note })}>
            Ignore
          </Button>
        )}
        {problem.status !== "fixed" && (
          <Button onClick={() => update.mutate({ status: "fixed", note })}>Mark fixed</Button>
        )}
      </div>
    </div>
  );
}

// --- Sign-in and security ------------------------------------------------------------------

function SchoolLinks({ schools }: { schools: { slug: string; name: string }[] }) {
  if (!schools.length) return <span className="text-neutral-500">—</span>;
  return (
    <>
      {schools.map((s, i) => (
        <span key={s.slug}>
          {i > 0 && ", "}
          <Link href={`/platform/schools/${s.slug}`} className="hover:underline">
            {s.name}
          </Link>
        </span>
      ))}
    </>
  );
}

const when = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Africa/Accra",
  }).format(new Date(iso));

function Security() {
  const [hours, setHours] = useState("24");
  const activity = useQuery({
    queryKey: ["platform", "security", hours],
    queryFn: () =>
      apiFetch<SecurityActivity>(`/api/v1/platform/system/security?hours=${hours}`, { school: false }),
    placeholderData: keepPreviousData,
  });
  if (activity.isPending) return <Loading />;
  if (activity.error) return <ErrorText error={activity.error} />;
  const a = activity.data;
  const suspicious = a.accounts.filter((x) => x.suspicious);
  return (
    <>
      <div className="mb-4 w-48">
        <Field label="Period">
          <Select value={hours} onChange={(e) => setHours(e.target.value)}>
            <option value="24">Last 24 hours</option>
            <option value="168">Last 7 days</option>
            <option value="720">Last 30 days</option>
          </Select>
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Failed sign-ins" value={a.failed_sign_ins} />
        <Stat label="Successful sign-ins" value={a.successful_sign_ins} />
        <Stat label="Accounts under attack" value={suspicious.length} hint="5 or more failed sign-ins" />
        <Stat label="Password resets" value={a.password_resets.length} />
      </div>
      {(suspicious.length > 0 || a.suspicious_addresses.length > 0) && (
        <div className="mt-4">
          <Alert tone="warning">
            {suspicious.length > 0 &&
              `${suspicious.length} account${suspicious.length === 1 ? " has" : "s have"} had 5 or more failed sign-ins. `}
            {a.suspicious_addresses.length > 0 &&
              `${a.suspicious_addresses.length} network address${a.suspicious_addresses.length === 1 ? " is" : "es are"} trying many different accounts.`}{" "}
            Contact the school if it isn't them.
          </Alert>
        </div>
      )}
      <div className="mt-6 grid gap-4">
        <Card title="Failed sign-ins by account">
          {a.accounts.length ? (
            <Table head={["Email tried", "Attempts", "From addresses", "Last attempt", "School"]}>
              {a.accounts.map((x) => (
                <tr key={x.email}>
                  <Td>
                    {x.email || "—"} {x.suspicious && <Badge tone="red">Repeated</Badge>}
                    {!x.known_account && (
                      <span className="block text-xs text-neutral-500">No account with this email</span>
                    )}
                  </Td>
                  <Td className="tabular-nums">{x.attempts}</Td>
                  <Td className="tabular-nums">{x.addresses}</Td>
                  <Td className="whitespace-nowrap">{when(x.last_attempt)}</Td>
                  <Td className="text-xs">
                    <SchoolLinks schools={x.schools} />
                  </Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty>No failed sign-ins in this period.</Empty>
          )}
        </Card>
        {a.suspicious_addresses.length > 0 && (
          <Card title="Addresses trying many accounts">
            <Table head={["Network address", "Accounts tried", "Attempts", "Last"]}>
              {a.suspicious_addresses.map((x) => (
                <tr key={x.ip}>
                  <Td className="font-mono text-xs">{x.ip}</Td>
                  <Td className="tabular-nums">{x.accounts}</Td>
                  <Td className="tabular-nums">{x.attempts}</Td>
                  <Td className="whitespace-nowrap">{when(x.last)}</Td>
                </tr>
              ))}
            </Table>
          </Card>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Password resets and changes">
            <EventList rows={a.password_resets} empty="No password activity in this period." />
          </Card>
          <Card title="Authenticator app changes">
            <EventList rows={a.authenticator_changes} empty="No authenticator changes in this period." />
          </Card>
        </div>
      </div>
    </>
  );
}

function EventList({ rows, empty }: { rows: SecurityActivity["password_resets"]; empty: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <ul className="divide-y divide-neutral-100 text-sm dark:divide-neutral-800">
      {rows.map((r) => (
        <li key={`${r.occurred_at}-${r.email}-${r.action}`} className="py-2">
          <span className="font-medium">{AUDIT_ACTIONS[r.action] ?? r.action}</span>
          <span className="text-neutral-600 dark:text-neutral-300"> · {r.email || "unknown"}</span>
          <span className="block text-xs text-neutral-500">
            {when(r.occurred_at)} · <SchoolLinks schools={r.schools} />
          </span>
        </li>
      ))}
    </ul>
  );
}

// --- Updates and health ------------------------------------------------------------------

function useSystemStatus() {
  return useQuery({
    queryKey: ["platform", "system"],
    queryFn: () => apiFetch<SystemStatus>("/api/v1/platform/system", { school: false }),
  });
}

function Updates() {
  const client = useQueryClient();
  const status = useSystemStatus();
  const check = useMutation({
    mutationFn: () => apiFetch<SystemStatus>("/api/v1/platform/system", { method: "POST", school: false }),
    onSuccess: (data) => {
      client.setQueryData(["platform", "system"], data);
      client.invalidateQueries({ queryKey: ["platform", "problems"] });
    },
  });
  if (status.isPending) return <Loading />;
  if (status.error) return <ErrorText error={status.error} />;
  const s = check.data ?? status.data;
  const failing = s.health?.filter((h) => !h.ok) ?? [];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Versions">
        <dl className="grid gap-2 text-sm">
          {[
            ["Nex Edu", `${s.app_version}${s.release ? ` (${s.release.slice(0, 12)})` : ""}`],
            ["Python", s.python],
            ["Django", s.django],
            ["School database version", s.schema_version],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3">
              <dt className="text-neutral-500">{label}</dt>
              <dd className="font-mono text-xs">{value}</dd>
            </div>
          ))}
        </dl>
        {s.debug && (
          <p className="mt-3">
            <Badge tone="amber">Development mode</Badge>
          </p>
        )}
      </Card>

      <Card
        title="School databases"
        actions={
          <Button variant="secondary" busy={check.isPending} onClick={() => check.mutate()}>
            Run health checks
          </Button>
        }
      >
        {s.schools_behind.length ? (
          <>
            <Alert tone="warning">
              {s.schools_behind.length} of {s.schools} school database{s.schools === 1 ? "" : "s"} need
              updating. Run <code>manage.py migrate_tenants</code>.
            </Alert>
            <ul className="mt-2 text-sm">
              {s.schools_behind.map((t) => (
                <li key={t.slug}>
                  <Link href={`/platform/schools/${t.slug}`} className="hover:underline">
                    {t.name}
                  </Link>{" "}
                  <span className="text-xs text-neutral-500">last updated {formatDate(t.migrated_at)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm">All {s.schools} school databases are up to date.</p>
        )}
        <ErrorText error={check.error} />
        {s.health && (
          <div className="mt-3">
            {failing.length ? (
              <Alert tone="error">
                {failing.length} check{failing.length === 1 ? "" : "s"} failed:{" "}
                {failing.map((h) => h.title).join("; ")}.
              </Alert>
            ) : (
              <Alert tone="success">All {s.health.length} health checks passed.</Alert>
            )}
          </div>
        )}
      </Card>

      <Card title="Security settings">
        <dl className="grid gap-2 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-neutral-500">Authenticator app for Nex Edu staff</dt>
            <dd>
              {s.platform_mfa_required ? (
                <Badge tone="green">Required</Badge>
              ) : (
                <Badge tone="amber">Optional</Badge>
              )}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-neutral-500">Authenticator app for school staff</dt>
            <dd>
              {s.school_mfa_roles.length ? (
                <Badge tone="green">Required for {s.school_mfa_roles.join(", ")}</Badge>
              ) : (
                <Badge tone="amber">Optional</Badge>
              )}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-neutral-500">Breached-password check</dt>
            <dd>
              {s.breached_password_check ? <Badge tone="green">On</Badge> : <Badge tone="red">Off</Badge>}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-xs text-neutral-500">
          Set on the server (PLATFORM_MFA_REQUIRED, MFA_REQUIRED_ROLES, BREACHED_PASSWORD_CHECK_ENABLED).
        </p>
      </Card>

      <Card title="Server security checks">
        {s.security_checks.length ? (
          <ul className="grid gap-2 text-sm">
            {s.security_checks.map((c) => (
              <li key={c.id}>
                <Badge tone={c.level === "error" ? "red" : "amber"}>{c.id}</Badge> {c.message}
                {c.hint && <span className="block text-xs text-neutral-500">{c.hint}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm">Django's security checks all pass.</p>
        )}
      </Card>
    </div>
  );
}

// --- Vulnerabilities ---------------------------------------------------------------------

function Vulnerabilities() {
  const client = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }) });
  const status = useSystemStatus();
  const [started, setStarted] = useState(false);
  const scan = useMutation({
    mutationFn: () => apiFetch("/api/v1/platform/system/scan", { method: "POST", school: false }),
    onSuccess: () => {
      setStarted(true);
      setTimeout(() => client.invalidateQueries({ queryKey: ["platform", "system"] }), 8_000);
    },
  });
  if (status.isPending) return <Loading />;
  if (status.error) return <ErrorText error={status.error} />;
  const s = status.data.scan;
  return (
    <Card
      title="Known vulnerabilities in the software Nex Edu runs on"
      actions={
        me.data?.platform_roles.includes("super_admin") && (
          <Button variant="secondary" busy={scan.isPending} onClick={() => scan.mutate()}>
            Scan now
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-neutral-600 dark:text-neutral-300">
        Every day the server checks each Python package it runs against OSV, the public database of security
        advisories. Web packages are checked on every code change (pnpm audit).
      </p>
      {started && <Alert tone="info">Scan started. Results appear here in a moment.</Alert>}
      <ErrorText error={scan.error} />
      {!s ? (
        <Empty>No scan yet.</Empty>
      ) : (
        <>
          <p className="mb-3 text-sm">
            Last scan {timeAgo(s.finished_at ?? s.started_at)} · {s.packages_checked} packages checked
          </p>
          {s.error ? (
            <Alert tone="warning">{s.error}. The next daily scan will try again.</Alert>
          ) : s.findings.length ? (
            <Table head={["Package", "Advisory", "What it is", "Fixed in"]}>
              {s.findings.map((f) => (
                <tr key={`${f.package}-${f.id}`}>
                  <Td>
                    <span className="font-medium">{f.package}</span>
                    <span className="block font-mono text-xs text-neutral-500">{f.version}</span>
                  </Td>
                  <Td>
                    <a href={f.url} target="_blank" rel="noreferrer" className="text-link underline">
                      {f.id}
                    </a>
                    {f.aliases.length > 0 && (
                      <span className="block text-xs text-neutral-500">{f.aliases.join(", ")}</span>
                    )}
                  </Td>
                  <Td className="text-xs">{f.summary || "—"}</Td>
                  <Td className="font-mono text-xs">{f.fixed_in.join(", ") || "No fix yet"}</Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Alert tone="success">No known vulnerabilities in the installed packages.</Alert>
          )}
        </>
      )}
    </Card>
  );
}
