"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { firstError, getSession, resetPassword } from "@/lib/allauth";

/** Where invitation and password-reset emails land. */
export default function SetPasswordPage() {
  const { key } = useParams<{ key: string }>();
  const [error, setError] = useState<string>();
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getSession(); // sets the CSRF cookie
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const password = String(form.get("password"));
    if (password !== String(form.get("confirm"))) {
      setError("The two passwords don't match.");
      return;
    }
    setBusy(true);
    const result = await resetPassword(decodeURIComponent(key), password);
    setBusy(false);
    // 401 with a pending "login" flow means success: the password is set, now sign in.
    if (result.status === 200 || result.status === 401) setDone(true);
    else setError(firstError(result) ?? "This link has expired or was already used.");
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-5 px-4">
      <h1 className="text-2xl font-semibold">Set your password</h1>
      {done ? (
        <Alert tone="success">
          Your password is set.{" "}
          <Link href="/login" className="font-medium underline">
            Sign in
          </Link>{" "}
          to continue.
        </Alert>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <p className="text-sm text-neutral-500">
            Use at least 12 characters. A short sentence you'll remember works well.
          </p>
          <Field label="New password">
            <Input name="password" type="password" autoComplete="new-password" minLength={12} required />
          </Field>
          <Field label="Confirm password">
            <Input name="confirm" type="password" autoComplete="new-password" minLength={12} required />
          </Field>
          {error && <Alert tone="error">{error}</Alert>}
          <Button type="submit" busy={busy}>
            Set password
          </Button>
        </form>
      )}
    </main>
  );
}
