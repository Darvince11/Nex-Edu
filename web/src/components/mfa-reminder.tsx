"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ShieldIcon } from "@/components/auth";
import type { Me } from "@/lib/api";

const SNOOZE_DAYS = 7;
const key = (userId: string) => `nexedu.mfa-reminder.${userId}`;

/**
 * A gentle nudge to add an authenticator app. Not a gate: "Not now" hides it on
 * this device for a week. Gone for good once an app is set up.
 */
export function MfaReminder({ me, message }: { me: Me; message: string }) {
  const [snoozed, setSnoozed] = useState(true); // hidden until storage is read, so it never flashes
  useEffect(() => {
    try {
      const until = Number(window.localStorage.getItem(key(me.id)) ?? 0);
      setSnoozed(until > Date.now());
    } catch {
      setSnoozed(false);
    }
  }, [me.id]);

  if (me.mfa_enrolled || snoozed) return null;

  const notNow = () => {
    setSnoozed(true);
    try {
      window.localStorage.setItem(key(me.id), String(Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000));
    } catch {
      // Storage blocked: hidden until the page reloads.
    }
  };

  return (
    <section
      aria-label="Account security"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-brand/20 bg-brand-50 px-4 py-2 text-sm dark:border-brand/30 dark:bg-brand/10"
    >
      <ShieldIcon className="size-4 shrink-0 text-brand dark:text-brand-bright" />
      <p className="min-w-0 flex-1 text-neutral-700 dark:text-neutral-200">{message}</p>
      <div className="flex items-center gap-2">
        <Link href="/security" className="font-medium text-link hover:text-link-hover">
          Set up
        </Link>
        <button
          type="button"
          onClick={notNow}
          className="rounded-control px-2 py-1 text-neutral-600 hover:bg-white hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
        >
          Not now
        </button>
      </div>
    </section>
  );
}
