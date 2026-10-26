"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  AuthField,
  AuthHeading,
  AuthShell,
  CheckCircleIcon,
  FormAlert,
  PasswordInput,
  Steps,
  SubmitButton,
  TextInput,
} from "@/components/auth";
import { activateTotp, firstError, getRecoveryCodes, getTotpSetup, reauthenticate } from "@/lib/allauth";

type Step = "loading" | "setup" | "codes" | "done";

/**
 * Staff must add an authenticator app before they can see school records.
 * Turning it on needs the password again (a fresh re-authentication), so a
 * borrowed, already-signed-in session can't be used to plant an attacker's device.
 * Recovery codes are shown once, straight after, because they are the only way
 * back in if the phone is lost.
 */
export default function SecurityPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("loading");
  const [secret, setSecret] = useState<string>();
  const [totpUrl, setTotpUrl] = useState<string>();
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getTotpSetup().then((r) => {
      if (r.status === 401 && !r.meta?.is_authenticated) router.replace("/login");
      else if (r.status === 404) {
        setSecret(r.meta?.secret as string);
        setTotpUrl(r.meta?.totp_url as string);
        setStep("setup");
      } else if (r.status === 200) setStep("done");
    });
  }, [router]);

  async function onTotp(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy(true);
    setError(undefined);
    try {
      const confirmed = await reauthenticate(String(form.get("password")));
      if (confirmed.status !== 200) {
        setError(firstError(confirmed) ?? "That password isn't right.");
        return;
      }
      const result = await activateTotp(String(form.get("code")).replace(/\s/g, ""));
      if (result.status !== 200) {
        setError(firstError(result) ?? "That code didn't work. Wait for the next one and try again.");
        return;
      }
      // The cached account still says "no second step"; refetch it everywhere.
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      const recovery = await getRecoveryCodes();
      const unused = (recovery.data?.unused_codes as string[] | undefined) ?? [];
      setCodes(unused);
      setStep(unused.length ? "codes" : "done");
    } catch {
      setError("We couldn't reach Nex Edu. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  function downloadCodes() {
    const text = `Nex Edu recovery codes\nEach code works once. Keep them somewhere safe and private.\n\n${codes.join("\n")}\n`;
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "nex-edu-recovery-codes.txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }

  return (
    <AuthShell>
      {step !== "loading" && step !== "done" && (
        <Steps steps={["Add the app", "Save recovery codes"]} current={step === "setup" ? 0 : 1} />
      )}
      {step === "loading" && <p className="text-sm text-neutral-500">Loading…</p>}

      {step === "setup" && secret && (
        <>
          <AuthHeading title="Protect your account">
            Staff accounts can see children's records, so they need a code from an authenticator app at
            sign-in.
          </AuthHeading>
          <ol className="mb-6 flex flex-col gap-3 text-sm text-neutral-600 dark:text-neutral-300">
            <li>1. Install Google Authenticator, Microsoft Authenticator or a similar app on your phone.</li>
            <li>
              2. In the app, add an account using this key{totpUrl ? ", or open the link on your phone" : ""}:
            </li>
          </ol>
          <code className="mb-2 block rounded-lg border border-neutral-200 bg-neutral-50 p-3 text-center font-mono text-base tracking-wider break-all dark:border-neutral-800 dark:bg-neutral-900">
            {secret}
          </code>
          {totpUrl && (
            <a
              href={totpUrl}
              className="mb-6 block text-center text-sm font-medium text-link hover:text-link-hover"
            >
              Open in authenticator app
            </a>
          )}
          <form onSubmit={onTotp} className="flex flex-col gap-5" noValidate>
            {error && <FormAlert>{error}</FormAlert>}
            <AuthField label="6-digit code from the app">
              {({ id }) => (
                <TextInput
                  id={id}
                  name="code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  className="text-center font-mono text-lg tracking-[0.3em]"
                />
              )}
            </AuthField>
            <AuthField
              label="Your password"
              hint="We ask again so nobody else can add their phone to your account."
            >
              {({ id, describedBy }) => (
                <PasswordInput
                  id={id}
                  name="password"
                  aria-describedby={describedBy}
                  autoComplete="current-password"
                  required
                />
              )}
            </AuthField>
            <SubmitButton busy={busy}>Turn on</SubmitButton>
          </form>
        </>
      )}

      {step === "codes" && (
        <>
          <AuthHeading title="Save your recovery codes">
            If you lose your phone, each of these codes lets you sign in once. This is the only time they're
            shown.
          </AuthHeading>
          <ul className="mb-5 grid grid-cols-2 gap-2 rounded-lg border border-neutral-200 bg-neutral-50 p-4 font-mono text-sm dark:border-neutral-800 dark:bg-neutral-900">
            {codes.map((code) => (
              <li key={code} className="text-center tracking-wider">
                {code}
              </li>
            ))}
          </ul>
          <button type="button" onClick={downloadCodes} className="btn-secondary mb-5 h-11 w-full">
            Download as a text file
          </button>
          <label className="mb-5 flex items-start gap-3 text-sm">
            <input
              type="checkbox"
              checked={saved}
              onChange={(e) => setSaved(e.target.checked)}
              className="mt-0.5 size-4 shrink-0 accent-brand"
            />
            <span className="text-neutral-600 dark:text-neutral-300">
              I've saved these codes somewhere safe and private, away from my phone.
            </span>
          </label>
          <button
            type="button"
            disabled={!saved}
            onClick={() => router.replace("/schools")}
            className="btn h-11 w-full"
          >
            Continue
          </button>
        </>
      )}

      {step === "done" && (
        <>
          <div className="mb-6 grid size-12 place-items-center rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            <CheckCircleIcon className="size-7" />
          </div>
          <AuthHeading title="Your account is protected">
            An authenticator app is set up. You'll enter a code from it each time you sign in.
          </AuthHeading>
          <button type="button" onClick={() => router.replace("/schools")} className="btn h-11 w-full">
            Continue
          </button>
        </>
      )}
    </AuthShell>
  );
}
