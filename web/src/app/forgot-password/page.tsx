"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useState } from "react";
import { AuthField, AuthHeading, AuthShell, FormAlert, SubmitButton, TextInput } from "@/components/auth";
import { getSession, requestPasswordReset } from "@/lib/allauth";
import { authError } from "@/lib/auth";

export default function ForgotPasswordPage() {
  return (
    <Suspense>
      <ForgotPassword />
    </Suspense>
  );
}

/** Same answer whether or not the email has an account, so it can't be used to probe. */
function ForgotPassword() {
  const [email, setEmail] = useState(useSearchParams().get("email") ?? "");
  const [sentTo, setSentTo] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getSession(); // sets the CSRF cookie
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(undefined);
    const address = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(address)) {
      setError("Enter a valid email address.");
      return;
    }
    setBusy(true);
    try {
      const result = await requestPasswordReset(address);
      if (result.status === 200) setSentTo(address);
      else setError(authError(result));
    } catch {
      setError("We couldn't reach Nex Edu. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell>
      {sentTo ? (
        <>
          <AuthHeading title="Check your email">
            If <span className="font-medium text-neutral-900 dark:text-neutral-100">{sentTo}</span> has a Nex
            Edu account, we've sent a link to choose a new password. It works once and expires in 3 days.
          </AuthHeading>
          <Link href="/login" className="btn-secondary h-11 w-full">
            Back to sign in
          </Link>
        </>
      ) : (
        <>
          <AuthHeading title="Reset your password">
            Enter the email you use for Nex Edu and we'll send you a reset link.
          </AuthHeading>
          <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
            <AuthField label="Email" error={error}>
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  aria-describedby={describedBy}
                  invalid={Boolean(error)}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  autoFocus
                  required
                />
              )}
            </AuthField>
            <SubmitButton busy={busy}>Send reset link</SubmitButton>
          </form>
          {error === undefined && (
            <FormAlert tone="info">
              <span className="block">Staff with a passkey can also sign in with it instead.</span>
            </FormAlert>
          )}
          <p className="mt-6 text-center text-sm text-neutral-500">
            Remembered it?{" "}
            <Link href="/login" className="font-medium text-brand hover:text-brand-strong">
              Sign in
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
