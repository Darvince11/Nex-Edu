"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, Suspense, useEffect, useState } from "react";
import {
  AuthField,
  AuthHeading,
  AuthShell,
  FormAlert,
  PasswordInput,
  SubmitButton,
  TextInput,
} from "@/components/auth";
import { VerifyEmailStep } from "@/components/verify-email";
import { type AuthResponse, getSession, login, logout, pendingFlow, submitMfaCode } from "@/lib/allauth";
import { authError, safeReturnTo } from "@/lib/auth";

type Step = "password" | "mfa" | "verify";

const REASONS: Record<string, string> = {
  not_authenticated: "Your session ended. Sign in again to continue.",
};

export default function LoginPage() {
  return (
    <Suspense>
      <SignIn />
    </Suspense>
  );
}

function SignIn() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeReturnTo(params.get("next"));
  const reason = params.get("reason");
  const [step, setStep] = useState<Step>("password");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<"password" | "mfa" | null>(null);

  useEffect(() => {
    getSession().then((r) => {
      if (r.meta?.is_authenticated) router.replace(next);
      else if (pendingFlow(r) === "mfa_authenticate") setStep("mfa");
      else if (pendingFlow(r) === "verify_email") setStep("verify");
    });
  }, [router, next]);

  function handle(result: AuthResponse) {
    if (result.meta?.is_authenticated) {
      router.replace(next);
      return;
    }
    const flow = pendingFlow(result);
    if (flow === "mfa_authenticate" || flow === "verify_email") {
      setError(undefined);
      setStep(flow === "mfa_authenticate" ? "mfa" : "verify");
      return;
    }
    setError(authError(result, "We couldn't sign you in. Check your details and try again."));
  }

  async function run(kind: "password" | "mfa", action: () => Promise<AuthResponse>) {
    setBusy(kind);
    setError(undefined);
    try {
      handle(await action());
    } catch {
      setError("We couldn't reach Nex Edu. Try again.");
    } finally {
      setBusy(null);
    }
  }

  async function startOver() {
    await logout();
    setCode("");
    setError(undefined);
    setStep("password");
  }

  function onPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    run("password", () => login(String(form.get("email")).trim(), String(form.get("password"))));
  }

  function onCode(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    run("mfa", () => submitMfaCode(code.replace(/\s/g, "")));
  }

  return (
    <AuthShell>
      {step === "verify" ? (
        <VerifyEmailStep email={email} onVerified={() => router.replace(next)} onRestart={startOver} />
      ) : step === "mfa" ? (
        <>
          <AuthHeading title="Two-step verification">
            Enter the 6-digit code from your authenticator app, or one of your recovery codes.
          </AuthHeading>
          <form onSubmit={onCode} className="flex flex-col gap-5" noValidate>
            <AuthField label="Code" error={error}>
              {({ id, describedBy }) => (
                <TextInput
                  id={id}
                  aria-describedby={describedBy}
                  invalid={Boolean(error)}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                  className="text-center font-mono text-lg tracking-[0.3em]"
                />
              )}
            </AuthField>
            <SubmitButton busy={busy === "mfa"}>Verify</SubmitButton>
          </form>
          <p className="mt-6 text-sm text-neutral-500">
            Lost your device? Use one of your recovery codes, or email support@nexedu.com.gh.{" "}
            <button type="button" onClick={startOver} className="font-medium text-link hover:text-link-hover">
              Start over
            </button>
          </p>
        </>
      ) : (
        <>
          <AuthHeading title="Welcome back">
            Sign in to run your school or follow your child's progress.
          </AuthHeading>
          <div className="flex flex-col gap-5">
            {reason && REASONS[reason] && <FormAlert tone="info">{REASONS[reason]}</FormAlert>}
            {error && <FormAlert>{error}</FormAlert>}
            <form onSubmit={onPassword} className="flex flex-col gap-5">
              <AuthField label="Email">
                {({ id }) => (
                  <TextInput
                    id={id}
                    name="email"
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                )}
              </AuthField>
              <AuthField
                label="Password"
                aside={
                  <Link
                    href={`/forgot-password${email ? `?email=${encodeURIComponent(email)}` : ""}`}
                    className="text-sm font-medium text-link hover:text-link-hover"
                  >
                    Forgot password?
                  </Link>
                }
              >
                {({ id }) => (
                  <PasswordInput id={id} name="password" autoComplete="current-password" required />
                )}
              </AuthField>
              <SubmitButton busy={busy === "password"}>Sign in</SubmitButton>
            </form>
          </div>
          <div className="mt-8 rounded-card border border-neutral-200 p-4 text-sm dark:border-neutral-800">
            <p className="font-medium">New to Nex Edu?</p>
            <p className="mt-1 text-neutral-500">
              School owners can{" "}
              <Link href="/signup" className="font-medium text-link hover:text-link-hover">
                register a school
              </Link>
              . Staff and parents: use the invitation email your school sent you.
            </p>
          </div>
        </>
      )}
    </AuthShell>
  );
}
