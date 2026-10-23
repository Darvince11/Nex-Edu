"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { Alert, Button, Field, Input } from "@/components/ui";
import { activateTotp, addPasskey, firstError, getTotpSetup, reauthenticate } from "@/lib/allauth";

/**
 * Staff must add a second factor before they can see school records.
 * Turning one on needs the password again (a fresh re-authentication), so a
 * borrowed, already-signed-in session can't be used to plant an attacker's device.
 */
export default function SecurityPage() {
  const router = useRouter();
  const [secret, setSecret] = useState<string>();
  const [totpUrl, setTotpUrl] = useState<string>();
  const [message, setMessage] = useState<{ tone: "error" | "success" | "info"; text: string }>();
  const [busy, setBusy] = useState<"totp" | "passkey" | null>(null);

  useEffect(() => {
    getTotpSetup().then((r) => {
      if (r.status === 401 && !r.meta?.is_authenticated) router.replace("/login");
      else if (r.status === 404) {
        setSecret(r.meta?.secret as string);
        setTotpUrl(r.meta?.totp_url as string);
      } else if (r.status === 200)
        setMessage({ tone: "info", text: "An authenticator app is already set up." });
    });
  }, [router]);

  async function confirmPassword(password: string): Promise<boolean> {
    const result = await reauthenticate(password);
    if (result.status === 200) return true;
    setMessage({ tone: "error", text: firstError(result) ?? "That password isn't right." });
    return false;
  }

  async function onTotp(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setBusy("totp");
    try {
      if (!(await confirmPassword(String(form.get("password"))))) return;
      const result = await activateTotp(String(form.get("code")).replace(/\s/g, ""));
      if (result.status === 200) {
        setMessage({ tone: "success", text: "Authenticator app is on. Taking you back…" });
        router.replace("/schools");
      } else {
        setMessage({ tone: "error", text: firstError(result) ?? "That code didn't work. Try the next one." });
      }
    } finally {
      setBusy(null);
    }
  }

  async function onPasskey(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const password = String(new FormData(e.currentTarget).get("password"));
    setBusy("passkey");
    try {
      if (!(await confirmPassword(password))) return;
      const result = await addPasskey("Passkey");
      if (result.status === 200) router.replace("/schools");
      else setMessage({ tone: "error", text: firstError(result) ?? "Could not add the passkey." });
    } catch {
      setMessage({ tone: "error", text: "Passkey setup was cancelled." });
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-8 px-4 py-10">
      <Logo className="h-12" />
      <div>
        <h1 className="text-2xl font-semibold">Protect your account</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Staff accounts can see children's records, so they need a second step at sign-in.
        </p>
      </div>
      {message && <Alert tone={message.tone}>{message.text}</Alert>}

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Passkey (recommended)</h2>
        <p className="text-sm text-neutral-500">
          Use your phone's fingerprint, face or screen lock. Nothing to type, and it can't be phished.
        </p>
        <form onSubmit={onPasskey} className="flex flex-col gap-3">
          <Field label="Your password">
            <Input name="password" type="password" autoComplete="current-password" required />
          </Field>
          <Button type="submit" busy={busy === "passkey"}>
            Add a passkey
          </Button>
        </form>
      </section>

      {secret && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-medium">Authenticator app</h2>
          <p className="text-sm text-neutral-500">
            In Google Authenticator, Microsoft Authenticator or similar, add an account with this key
            {totpUrl ? " (or open the link on your phone)" : ""}:
          </p>
          <code className="rounded-md bg-neutral-100 p-3 text-center font-mono tracking-wider break-all dark:bg-neutral-900">
            {secret}
          </code>
          {totpUrl && (
            <a href={totpUrl} className="text-center text-sm underline">
              Open in authenticator app
            </a>
          )}
          <form onSubmit={onTotp} className="flex flex-col gap-3">
            <Field label="Your password">
              <Input name="password" type="password" autoComplete="current-password" required />
            </Field>
            <Field label="6-digit code from the app">
              <Input name="code" inputMode="numeric" autoComplete="one-time-code" required />
            </Field>
            <Button type="submit" variant="secondary" busy={busy === "totp"}>
              Turn on
            </Button>
          </form>
        </section>
      )}
    </main>
  );
}
