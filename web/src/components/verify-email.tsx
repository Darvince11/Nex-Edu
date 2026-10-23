"use client";

import { type FormEvent, useEffect, useState } from "react";
import { resendEmailCode, verifyEmail } from "@/lib/allauth";
import { authError } from "@/lib/auth";
import { AuthField, AuthHeading, EmailCodeInput, FormAlert, SubmitButton } from "./auth";

/** Matches the server's limit of one new code per minute per email. */
const RESEND_SECONDS = 60;

/**
 * Enter the 8-letter code we emailed. Three wrong codes end the attempt
 * (server-side), after which the person starts again for a fresh code.
 */
export function VerifyEmailStep({
  email,
  onVerified,
  onRestart,
}: {
  email?: string;
  onVerified: () => void;
  onRestart: () => void;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [expired, setExpired] = useState(false);
  const [cooldown, setCooldown] = useState(RESEND_SECONDS);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setNotice(undefined);
    if (code.replace("-", "").length !== 8) {
      setError("Enter the 8-letter code from the email.");
      return;
    }
    setBusy(true);
    try {
      const result = await verifyEmail(code);
      if (result.meta?.is_authenticated) return onVerified();
      if (result.status === 409) {
        setExpired(true);
        setError("This code can't be used any more. Start again to get a new one.");
      } else {
        setError(authError(result));
      }
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(undefined);
    const result = await resendEmailCode();
    if (result.status === 200) {
      setNotice("We sent a new code. Older codes no longer work.");
      setCode("");
      setCooldown(RESEND_SECONDS);
    } else if (result.status === 409) {
      setExpired(true);
      setError("This sign-up has expired. Start again to get a new code.");
    } else {
      setError(authError(result));
    }
  }

  return (
    <>
      <AuthHeading title="Check your email">
        We sent an 8-letter code to{" "}
        <span className="font-medium text-neutral-900 dark:text-neutral-100">
          {email || "your email address"}
        </span>
        . It expires in 15 minutes.
      </AuthHeading>
      <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
        <AuthField label="Verification code" error={error}>
          {({ id, describedBy }) => (
            <EmailCodeInput
              id={id}
              aria-describedby={describedBy}
              invalid={Boolean(error)}
              value={code}
              onChange={setCode}
              disabled={expired}
              autoFocus
            />
          )}
        </AuthField>
        {notice && <FormAlert tone="success">{notice}</FormAlert>}
        {expired ? (
          <button type="button" className="btn h-11 w-full" onClick={onRestart}>
            Start again
          </button>
        ) : (
          <SubmitButton busy={busy}>Verify email</SubmitButton>
        )}
      </form>
      <div className="mt-6 flex flex-col gap-2 text-sm text-neutral-500">
        <p>
          Didn't get it? Check your spam folder, or{" "}
          <button
            type="button"
            onClick={resend}
            disabled={cooldown > 0 || expired}
            className="font-medium text-brand hover:text-brand-strong disabled:cursor-not-allowed disabled:text-neutral-400"
          >
            {cooldown > 0 ? `send a new code in ${cooldown}s` : "send a new code"}
          </button>
          .
        </p>
        <p>
          Wrong email?{" "}
          <button
            type="button"
            onClick={onRestart}
            className="font-medium text-brand hover:text-brand-strong"
          >
            Start again
          </button>
        </p>
      </div>
    </>
  );
}
