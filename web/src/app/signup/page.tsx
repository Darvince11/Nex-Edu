"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";
import {
  AuthField,
  AuthHeading,
  AuthShell,
  FormAlert,
  PasswordChecklist,
  PasswordInput,
  Steps,
  SubmitButton,
  TextInput,
} from "@/components/auth";
import { RegisterSchoolForm, RegistrationStatus } from "@/components/register-school";
import { VerifyEmailStep } from "@/components/verify-email";
import { getSession, logout, pendingFlow, signup } from "@/lib/allauth";
import { ApiError, apiFetch, type Registration } from "@/lib/api";
import { authError, fieldErrors, passwordAcceptable, passwordRules } from "@/lib/auth";

type Step = "loading" | "account" | "verify" | "school" | "done";
const STEPS = ["Your account", "Verify email", "Your school"];
const STEP_INDEX: Record<Step, number> = { loading: 0, account: 0, verify: 1, school: 2, done: 3 };

/**
 * School owner sign-up. Creating an account opens nothing by itself: the owner
 * verifies their email, describes the school, and Nex Edu staff approve it
 * before any school workspace exists.
 */
export default function SignupPage() {
  const [step, setStep] = useState<Step>("loading");
  const [email, setEmail] = useState("");
  const [registration, setRegistration] = useState<Registration>();

  async function resume() {
    const session = await getSession();
    if (pendingFlow(session) === "verify_email") return setStep("verify");
    if (!session.meta?.is_authenticated) return setStep("account");
    try {
      const mine = await apiFetch<Registration[]>("/api/v1/registrations", { school: false });
      const live = mine.find((r) => r.status === "pending" || r.status === "approved") ?? mine[0];
      if (live && live.status !== "rejected") {
        setRegistration(live);
        return setStep("done");
      }
      setStep("school");
    } catch (error) {
      // Signed in but not verified yet, or the API is unreachable.
      setStep(error instanceof ApiError && error.code === "email_unverified" ? "verify" : "school");
    }
  }

  // biome-ignore lint/correctness/useExhaustiveDependencies: run once on load.
  useEffect(() => {
    void resume();
  }, []);

  async function restart() {
    await logout();
    setEmail("");
    setStep("account");
  }

  return (
    <AuthShell wide={step === "school"}>
      {step !== "done" && step !== "loading" && <Steps steps={STEPS} current={STEP_INDEX[step]} />}
      {step === "loading" && <p className="text-sm text-neutral-500">Loading…</p>}
      {step === "account" && (
        <AccountStep
          onCreated={(address) => {
            setEmail(address);
            setStep("verify");
          }}
        />
      )}
      {step === "verify" && (
        <VerifyEmailStep email={email} onVerified={() => void resume()} onRestart={restart} />
      )}
      {step === "school" && (
        <RegisterSchoolForm
          onSubmitted={(r) => {
            setRegistration(r);
            setStep("done");
          }}
        />
      )}
      {step === "done" && registration && <RegistrationStatus registration={registration} />}
    </AuthShell>
  );
}

function AccountStep({ onCreated }: { onCreated: (email: string) => void }) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const rules = passwordRules(password, { email, names: [firstName, lastName] });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setFormError(undefined);
    const local: Record<string, string> = {};
    if (!firstName.trim()) local.first_name = "Enter your first name.";
    if (!lastName.trim()) local.last_name = "Enter your last name.";
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) local.email = "Enter a valid email address.";
    if (!passwordAcceptable(rules)) local.password = "Choose a password that meets the rules below.";
    if (!accepted) local.accept_terms = "Agree to the terms and privacy notice to continue.";
    setErrors(local);
    if (Object.keys(local).length) return;

    setBusy(true);
    try {
      const result = await signup({
        email: email.trim(),
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        accept_terms: accepted,
        website: String(form.get("website") ?? ""),
      });
      if (pendingFlow(result) === "verify_email" || result.meta?.is_authenticated) {
        onCreated(email.trim());
        return;
      }
      const byField = fieldErrors(result);
      setErrors(byField);
      if (!Object.keys(byField).length)
        setFormError(authError(result, "We couldn't create your account. Try again."));
    } catch {
      setFormError("We couldn't reach Nex Edu. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AuthHeading title="Register your school">
        Start with your own account. We'll email you a code to confirm it's you.
      </AuthHeading>
      <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
        {formError && <FormAlert>{formError}</FormAlert>}
        <div className="grid gap-5 sm:grid-cols-2">
          <AuthField label="First name" error={errors.first_name}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                aria-describedby={describedBy}
                invalid={Boolean(errors.first_name)}
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                autoComplete="given-name"
                maxLength={150}
                required
              />
            )}
          </AuthField>
          <AuthField label="Last name" error={errors.last_name}>
            {({ id, describedBy }) => (
              <TextInput
                id={id}
                aria-describedby={describedBy}
                invalid={Boolean(errors.last_name)}
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                autoComplete="family-name"
                maxLength={150}
                required
              />
            )}
          </AuthField>
        </div>
        <AuthField
          label="Email"
          error={errors.email}
          hint="Use an address only you can read. We'll send your code here."
        >
          {({ id, describedBy }) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              invalid={Boolean(errors.email)}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          )}
        </AuthField>
        <AuthField label="Password" error={errors.password} hint={<PasswordChecklist rules={rules} />}>
          {({ id, describedBy }) => (
            <PasswordInput
              id={id}
              aria-describedby={describedBy}
              invalid={Boolean(errors.password)}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              required
            />
          )}
        </AuthField>

        {/* Honeypot: invisible to people and screen readers; bots fill it in. */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
          <label>
            Website
            <input name="website" type="text" tabIndex={-1} autoComplete="off" defaultValue="" />
          </label>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              aria-invalid={Boolean(errors.accept_terms) || undefined}
              className="mt-0.5 size-4 shrink-0 accent-brand"
            />
            <span className="text-neutral-600 dark:text-neutral-300">
              I agree to the{" "}
              <Link
                href="/legal/terms"
                target="_blank"
                className="font-medium text-brand underline-offset-2 hover:underline"
              >
                terms of service
              </Link>{" "}
              and have read the{" "}
              <Link
                href="/legal/privacy"
                target="_blank"
                className="font-medium text-brand underline-offset-2 hover:underline"
              >
                privacy notice
              </Link>
              , which explains how Nex Edu handles personal data under Ghana's Data Protection Act.
            </span>
          </label>
          {errors.accept_terms && (
            <p className="text-xs font-medium text-red-700 dark:text-red-400">{errors.accept_terms}</p>
          )}
        </div>

        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>
      <p className="mt-6 text-center text-sm text-neutral-500">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand hover:text-brand-strong">
          Sign in
        </Link>
      </p>
    </>
  );
}
