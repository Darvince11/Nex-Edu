"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, type ReactNode, useState } from "react";
import { initials } from "@/components/account-controls";
import { PasswordChecklist, PasswordInput } from "@/components/auth";
import { useTheme } from "@/components/theme-toggle";
import { Alert, Badge, Button, Card, ErrorText, Field, Input, PageHeader } from "@/components/ui";
import { changePassword, firstError } from "@/lib/allauth";
import { apiFetch, type Me } from "@/lib/api";
import { passwordAcceptable, passwordRules } from "@/lib/auth";
import type { Theme } from "@/lib/theme";

/**
 * The signed-in person's own account: their details, password, two-step sign-in
 * and appearance. `access` lists what they can do where this page is shown (their
 * school's roles, or their platform roles); other schools are never listed.
 */
export function ProfilePage({
  me,
  access,
  emailNote,
  links,
  extra,
}: {
  me: Me;
  access: { label: string; roles: string[] };
  emailNote: string;
  links?: { href: string; label: string; description: string }[];
  /** More cards for the side column (the school profile adds calendar and notifications). */
  extra?: ReactNode;
}) {
  return (
    <>
      <PageHeader
        title="Your profile"
        description="Your own account. Changes here apply wherever you sign in."
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="grid content-start gap-4">
          <DetailsCard me={me} emailNote={emailNote} />
          <PasswordCard me={me} />
        </div>
        <div className="grid content-start gap-4">
          <Card title="Access">
            <p className="text-sm text-neutral-500">{access.label}</p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {access.roles.map((role) => (
                <li key={role}>
                  <Badge tone="blue">{role}</Badge>
                </li>
              ))}
            </ul>
          </Card>
          <SecurityCard me={me} />
          {extra}
          <AppearanceCard />
          {links?.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="flex items-center justify-between gap-3 rounded-card border border-brand/30 bg-brand/5 p-4 hover:border-brand dark:bg-brand/10"
            >
              <span>
                <span className="block font-medium">{link.label}</span>
                <span className="text-sm text-neutral-500">{link.description}</span>
              </span>
              <span aria-hidden="true" className="text-link">
                →
              </span>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}

function DetailsCard({ me, emailNote }: { me: Me; emailNote: string }) {
  const client = useQueryClient();
  const [form, setForm] = useState({ first_name: me.first_name, last_name: me.last_name, phone: me.phone });
  const changed = (Object.keys(form) as (keyof typeof form)[]).filter((k) => form[k] !== me[k]);
  const save = useMutation({
    mutationFn: () =>
      apiFetch<Me>("/api/v1/me", {
        method: "PATCH",
        school: false,
        body: Object.fromEntries(changed.map((k) => [k, form[k]])),
      }),
    onSuccess: (data) => {
      client.setQueryData(["me"], data);
      setForm({ first_name: data.first_name, last_name: data.last_name, phone: data.phone });
    },
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => {
    save.reset();
    setForm((f) => ({ ...f, [key]: e.target.value }));
  };

  return (
    <Card title="Personal details">
      <div className="mb-4 flex items-center gap-3">
        <span
          aria-hidden="true"
          className="grid size-14 place-items-center rounded-full bg-brand text-lg font-semibold text-white"
        >
          {initials(me)}
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium">{`${me.first_name} ${me.last_name}`.trim() || me.email}</p>
          <p className="truncate text-sm text-neutral-500">{me.email}</p>
        </div>
      </div>
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          if (changed.length) save.mutate();
        }}
      >
        <Field label="First name">
          <Input value={form.first_name} onChange={set("first_name")} autoComplete="given-name" required />
        </Field>
        <Field label="Last name">
          <Input value={form.last_name} onChange={set("last_name")} autoComplete="family-name" required />
        </Field>
        <Field label="Phone" hint="Ghana number, e.g. 024 412 3456. Used for school messages.">
          <Input value={form.phone} onChange={set("phone")} type="tel" autoComplete="tel" inputMode="tel" />
        </Field>
        <Field label="Email" hint={emailNote}>
          <Input
            value={me.email}
            readOnly
            aria-readonly="true"
            className="bg-neutral-50 dark:bg-neutral-800/50"
          />
        </Field>
        <div className="flex items-center justify-end gap-3 sm:col-span-2">
          {save.isSuccess && (
            <span role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
              Saved
            </span>
          )}
          <ErrorText error={save.error} />
          <Button type="submit" busy={save.isPending} disabled={!changed.length}>
            Save changes
          </Button>
        </div>
      </form>
    </Card>
  );
}

function PasswordCard({ me }: { me: Me }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const rules = passwordRules(next, { email: me.email, names: [me.first_name, me.last_name] });
  const mismatch = confirm.length > 0 && confirm !== next;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!passwordAcceptable(rules) || mismatch) return;
    setBusy(true);
    setError(undefined);
    const result = await changePassword(current, next);
    setBusy(false);
    if (result.status === 200) {
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } else {
      setError(firstError(result) ?? "We couldn't change your password. Try again.");
    }
  }

  return (
    <Card title="Password">
      <form className="grid gap-3" onSubmit={submit}>
        {done && <Alert tone="success">Password changed. You've been signed out everywhere else.</Alert>}
        {error && <Alert tone="error">{error}</Alert>}
        <Field label="Current password">
          <PasswordInput
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="New password">
            <PasswordInput
              value={next}
              onChange={(e) => {
                setDone(false);
                setNext(e.target.value);
              }}
              autoComplete="new-password"
              required
            />
          </Field>
          <Field label="Confirm new password">
            <PasswordInput
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              invalid={mismatch}
              required
            />
          </Field>
        </div>
        {next && <PasswordChecklist rules={rules} />}
        {mismatch && <p className="text-xs text-red-700 dark:text-red-400">The passwords don't match.</p>}
        <div className="flex justify-end">
          <Button
            type="submit"
            busy={busy}
            disabled={!current || !passwordAcceptable(rules) || confirm !== next}
          >
            Change password
          </Button>
        </div>
      </form>
    </Card>
  );
}

function SecurityCard({ me }: { me: Me }) {
  const lastSignIn = me.last_login
    ? new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Africa/Accra",
      }).format(new Date(me.last_login))
    : "First sign-in";
  return (
    <Card title="Sign-in and security">
      <dl className="grid gap-3 text-sm">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-neutral-500">Two-step sign-in</dt>
          <dd>{me.mfa_enrolled ? <Badge tone="green">On</Badge> : <Badge tone="amber">Not set up</Badge>}</dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-neutral-500">Last sign-in</dt>
          <dd className="text-right tabular-nums">{lastSignIn}</dd>
        </div>
      </dl>
      <Link href="/security" className="mt-4 inline-flex text-sm font-medium text-link hover:text-link-hover">
        {me.mfa_enrolled ? "Manage authenticator app and recovery codes" : "Set up an authenticator app"}
      </Link>
    </Card>
  );
}

function AppearanceCard() {
  const [theme, setTheme] = useTheme();
  const options: { value: Theme; label: string }[] = [
    { value: "light", label: "Light" },
    { value: "dark", label: "Dark" },
  ];
  return (
    <Card title="Appearance">
      <fieldset>
        <legend className="sr-only">Theme</legend>
        <div className="grid grid-cols-2 gap-2">
          {options.map((option) => (
            <label
              key={option.value}
              className={`flex cursor-pointer items-center gap-2 rounded-control border p-3 text-sm font-medium has-focus-visible:outline-2 has-focus-visible:outline-brand ${
                theme === option.value
                  ? "border-brand bg-brand/5 dark:bg-brand/15"
                  : "border-neutral-300 hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              }`}
            >
              <input
                type="radio"
                name="theme"
                value={option.value}
                checked={theme === option.value}
                onChange={() => setTheme(option.value)}
                className="sr-only"
              />
              <span
                aria-hidden="true"
                className={`size-5 rounded-full border ${option.value === "dark" ? "border-neutral-600 bg-neutral-900" : "border-neutral-300 bg-white"}`}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
      <p className="mt-2 text-xs text-neutral-500">Remembered on this device.</p>
    </Card>
  );
}
