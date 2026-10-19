"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import {
  activateTotp,
  addPasskey,
  firstError,
  getTotpSetup,
  pendingFlow,
  reauthenticate,
} from "@/lib/allauth";

export default function SecurityPage() {
  const router = useRouter();
  const [secret, setSecret] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [needsPassword, setNeedsPassword] = useState(false);

  useEffect(() => {
    getTotpSetup().then((r) => {
      if (r.status === 401 && !r.meta?.is_authenticated) router.replace("/login");
      else if (r.status === 404) setSecret(r.meta?.secret as string);
      else if (r.status === 200) setMessage("An authenticator app is already set up.");
    });
  }, [router]);

  async function onTotp(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code")).replace(/\s/g, "");
    const result = await activateTotp(code);
    if (result.status === 200) router.replace("/schools");
    else setMessage(firstError(result) ?? "That code didn't work. Try the next one.");
  }

  async function onPasskey() {
    try {
      const result = await addPasskey("Passkey");
      if (pendingFlow(result) === "reauthenticate" || result.status === 401) {
        setNeedsPassword(true);
        setMessage("Confirm your password, then add the passkey again.");
      } else if (result.status === 200) {
        router.replace("/schools");
      } else {
        setMessage(firstError(result) ?? "Could not add the passkey.");
      }
    } catch {
      setMessage("Passkey setup was cancelled.");
    }
  }

  async function onReauth(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const result = await reauthenticate(String(new FormData(e.currentTarget).get("password")));
    if (result.status === 200) {
      setNeedsPassword(false);
      await onPasskey();
    } else setMessage(firstError(result) ?? "Incorrect password.");
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-8 px-4 py-10">
      <h1 className="text-2xl font-semibold">Protect your account</h1>
      {message && (
        <p role="status" className="rounded-md bg-neutral-100 p-3 text-sm dark:bg-neutral-900">
          {message}
        </p>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium">Passkey (recommended)</h2>
        <p className="text-sm text-neutral-500">
          Use your phone's fingerprint, face or screen lock. Nothing to type, and it can't be phished.
        </p>
        {needsPassword ? (
          <form onSubmit={onReauth} className="flex flex-col gap-3">
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              className="input"
            />
            <button type="submit" className="btn">
              Confirm password
            </button>
          </form>
        ) : (
          <button type="button" className="btn" onClick={onPasskey}>
            Add a passkey
          </button>
        )}
      </section>

      {secret && (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-medium">Authenticator app</h2>
          <p className="text-sm text-neutral-500">
            In Google Authenticator, Microsoft Authenticator or similar, add an account with this key:
          </p>
          <code className="rounded-md bg-neutral-100 p-3 text-center font-mono tracking-wider break-all dark:bg-neutral-900">
            {secret}
          </code>
          <form onSubmit={onTotp} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Enter the 6-digit code it shows
              <input
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                className="input"
              />
            </label>
            <button type="submit" className="btn-secondary">
              Turn on
            </button>
          </form>
        </section>
      )}
    </main>
  );
}
