"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  type AuthResponse,
  firstError,
  getSession,
  login,
  loginWithPasskey,
  pendingFlow,
  submitMfaCode,
} from "@/lib/allauth";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<"password" | "mfa">("password");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getSession().then((r) => {
      if (r.meta?.is_authenticated) router.replace("/schools");
    });
  }, [router]);

  function handle(result: AuthResponse) {
    if (result.meta?.is_authenticated) {
      router.replace("/schools");
    } else if (pendingFlow(result) === "mfa_authenticate") {
      setStep("mfa");
      setError(undefined);
    } else {
      setError(firstError(result) ?? "Sign-in failed. Check your details and try again.");
    }
  }

  async function run(action: () => Promise<AuthResponse>) {
    setBusy(true);
    try {
      handle(await action());
    } catch {
      setError("Sign-in was cancelled or failed.");
    } finally {
      setBusy(false);
    }
  }

  function onPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    run(() => login(String(form.get("email")), String(form.get("password"))));
  }

  function onCode(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    run(() => submitMfaCode(String(form.get("code")).replace(/\s/g, "")));
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 px-4">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      {error && (
        <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      {step === "password" ? (
        <>
          <button type="button" className="btn" disabled={busy} onClick={() => run(loginWithPasskey)}>
            Sign in with a passkey
          </button>
          <div className="text-center text-sm text-neutral-500">or use your password</div>
          <form onSubmit={onPassword} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Email
              <input name="email" type="email" autoComplete="username webauthn" required className="input" />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Password
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                required
                className="input"
              />
            </label>
            <button type="submit" className="btn-secondary" disabled={busy}>
              Continue
            </button>
          </form>
        </>
      ) : (
        <form onSubmit={onCode} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Code from your authenticator app or a recovery code
            <input name="code" inputMode="numeric" autoComplete="one-time-code" required className="input" />
          </label>
          <button type="submit" className="btn" disabled={busy}>
            Verify
          </button>
        </form>
      )}
    </main>
  );
}
