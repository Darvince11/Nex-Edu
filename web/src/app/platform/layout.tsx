"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import { AccountControls } from "@/components/account-controls";
import { Logo } from "@/components/brand";
import { MfaReminder } from "@/components/mfa-reminder";
import { PlatformNav } from "@/components/platform-nav";
import { ApiError, apiFetch, type Me, type Paged, type PlatformRegistration } from "@/lib/api";
import { loginPath } from "@/lib/auth";
import { platformNavFor } from "@/lib/platform";
import { PLATFORM_ROLE_LABELS } from "@/lib/roles";

const hasRole = (me: Me | undefined, roles: string[]) =>
  Boolean(me?.platform_roles.some((r) => roles.includes(r)));

/**
 * Nex Edu's operator console. The menu and the "staff only" screen are
 * conveniences: every /api/v1/platform/ call is checked by IsPlatformStaff.
 */
export default function PlatformLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }),
  });
  const isStaff = Boolean(me.data?.platform_roles.length);
  const pending = useQuery({
    queryKey: ["platform", "registrations", "pending"],
    queryFn: () =>
      apiFetch<Paged<PlatformRegistration>>("/api/v1/platform/registrations?status=pending", {
        school: false,
      }),
    enabled: isStaff && hasRole(me.data, ["super_admin", "support"]),
    refetchInterval: 60_000,
  });
  const openProblems = useQuery({
    queryKey: ["platform", "problems", "count"],
    queryFn: () => apiFetch<{ open: number }>("/api/v1/platform/system/problems", { school: false }),
    enabled: isStaff && hasRole(me.data, ["super_admin", "support"]),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) router.replace(loginPath(me.error.code));
  }, [me.error, router]);

  if (me.isPending) return <p className="p-6 text-sm text-neutral-500">Loading…</p>;
  if (!me.data) return <p className="p-6 text-sm text-neutral-500">Could not load your account.</p>;

  if (!isStaff) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-4 px-4">
        <Logo className="h-11" />
        <h1 className="text-2xl font-semibold">Platform staff only</h1>
        <p className="text-sm text-neutral-500">
          This area is for the Nex Edu team. If you run a school, go to your school instead.
        </p>
        <Link href="/schools" className="btn h-11">
          Go to my school
        </Link>
      </main>
    );
  }

  const groups = platformNavFor(me.data.platform_roles);
  const badges = {
    registrations: pending.data?.results.length
      ? { text: `${pending.data.results.length}${pending.data.next ? "+" : ""}`, label: "waiting" }
      : undefined,
    problems: openProblems.data?.open
      ? { text: String(openProblems.data.open), label: "open problems" }
      : undefined,
  };

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="border-b border-neutral-200 bg-white p-4 lg:border-r lg:border-b-0 dark:border-neutral-800 dark:bg-neutral-950">
        <div className="mb-4 flex items-center justify-between gap-3 lg:block">
          <Link href="/platform" aria-label="Nex Edu platform dashboard">
            <Logo className="h-10" />
          </Link>
          <span className="inline-flex rounded-md bg-brand-navy px-2 py-0.5 text-xs font-semibold tracking-wide text-white uppercase lg:mt-3">
            Platform
          </span>
        </div>
        <PlatformNav groups={groups} pathname={pathname} badges={badges} />
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-white px-4 py-3 text-sm dark:border-neutral-800 dark:bg-neutral-950">
          <span className="min-w-0 truncate text-neutral-500">
            {me.data.platform_roles.map((r) => PLATFORM_ROLE_LABELS[r] ?? r).join(", ")}
          </span>
          <AccountControls me={me.data} profileHref="/platform/profile" />
        </header>
        <MfaReminder
          me={me.data}
          message="Add an authenticator app for a second sign-in step. This account can see every school, so it's worth doing."
        />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      </div>
    </div>
  );
}
