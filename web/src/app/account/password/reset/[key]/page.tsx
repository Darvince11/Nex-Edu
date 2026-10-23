"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  AuthField,
  AuthHeading,
  AuthShell,
  CheckCircleIcon,
  FormAlert,
  PasswordChecklist,
  PasswordInput,
  SubmitButton,
} from "@/components/auth";
import { getSession, resetPassword } from "@/lib/allauth";
import { authError, passwordAcceptable, passwordRules } from "@/lib/auth";

/** Where invitation and password-reset emails land. The link works once. */
export default function SetPasswordPage() {
  const { key } = useParams<{ key: string }>();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const rules = passwordRules(password);

  useEffect(() => {
    void getSession(); // sets the CSRF cookie
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!passwordAcceptable(rules)) {
      setError("Choose a password that meets the rules below.");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      const result = await resetPassword(decodeURIComponent(key), password);
      // 401 with a pending "login" flow means success: the password is set, now sign in.
      if (result.status === 200 || result.status === 401) setDone(true);
      else setError(authError(result, "This link has expired or was already used. Ask for a new one."));
    } catch {
      setError("We couldn't reach Nex Edu. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      {done ? (
        <>
          <div className="mb-6 grid size-12 place-items-center rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            <CheckCircleIcon className="size-7" />
          </div>
          <AuthHeading title="Your password is set">
            Sign in with it now. Staff will then set up a passkey or authenticator app.
          </AuthHeading>
          <Link href="/login" className="btn h-11 w-full">
            Sign in
          </Link>
        </>
      ) : (
        <>
          <AuthHeading title="Choose a password">
            Four or more unrelated words you'll remember work well. Don't reuse a password from another site.
          </AuthHeading>
          <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
            {error && <FormAlert>{error}</FormAlert>}
            <AuthField label="New password" hint={<PasswordChecklist rules={rules} />}>
              {({ id, describedBy }) => (
                <PasswordInput
                  id={id}
                  aria-describedby={describedBy}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  autoFocus
                  required
                />
              )}
            </AuthField>
            <SubmitButton busy={busy}>Set password</SubmitButton>
          </form>
          <p className="mt-6 text-center text-sm text-neutral-500">
            Link expired?{" "}
            <Link href="/forgot-password" className="font-medium text-brand hover:text-brand-strong">
              Get a new one
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
