"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Logo } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { logout } from "@/lib/allauth";
import { ApiError, apiFetch, getSelectedSchool, type Me, type Registration, selectSchool } from "@/lib/api";
import { loginPath, SCHOOL_DOMAIN } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { pickSchool } from "@/lib/school";

/**
 * Where sign-in lands. Nobody picks a school here: people who belong to one go
 * straight to it (see pickSchool), Nex Edu staff with no school go to the
 * console, and everyone else sees how their registration or invitation stands.
 */
export default function SchoolsPage() {
  const router = useRouter();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }),
  });
  const noSchools = me.data?.schools.length === 0;
  const platformOnly = noSchools && Boolean(me.data?.platform_roles.length);
  const registrations = useQuery({
    queryKey: ["registrations"],
    queryFn: () => apiFetch<Registration[]>("/api/v1/registrations", { school: false }),
    enabled: noSchools && !platformOnly,
  });

  useEffect(() => {
    if (me.error instanceof ApiError && [401, 403].includes(me.error.status)) {
      router.replace(loginPath(me.error.code));
      return;
    }
    if (!me.data) return;
    const slug = pickSchool(me.data, getSelectedSchool());
    if (slug) {
      selectSchool(slug);
      router.replace("/dashboard");
    } else if (me.data.platform_roles.length) {
      router.replace("/platform");
    }
  }, [me.data, me.error, router]);

  if (me.isPending || (me.data && (!noSchools || platformOnly))) {
    return (
      <main className="grid min-h-dvh place-items-center px-4">
        <div className="flex flex-col items-center gap-4 text-sm text-neutral-500" role="status">
          <Logo className="h-11" />
          Signing you in…
        </div>
      </main>
    );
  }
  if (!me.data) return <p className="p-6">Could not load your account.</p>;

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  const latest = registrations.data?.[0];
  const unavailable = me.data.unavailable_schools ?? [];

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between gap-4">
        <Logo className="h-12" />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            type="button"
            onClick={signOut}
            className="text-sm font-medium text-neutral-500 hover:text-link"
          >
            Sign out
          </button>
        </div>
      </div>
      <h1 className="text-2xl font-semibold">Your account</h1>
      <p className="mt-1 text-neutral-500">Signed in as {me.data.email}</p>

      {unavailable.map((s) => (
        <section
          key={s.slug}
          aria-label={s.name}
          className="mt-6 rounded-card border border-amber-300 bg-amber-50 p-5 dark:border-amber-800 dark:bg-amber-950/40"
        >
          <p className="font-medium">
            {s.name} is {s.status === "suspended" ? "suspended" : "closed"}
          </p>
          <p className="mt-1 text-sm text-neutral-700 dark:text-neutral-300">
            {s.status === "suspended"
              ? s.unpaid
                ? "A Nex Edu invoice is more than 30 days overdue. Nobody at the school can sign in until it's paid."
                : "Nex Edu has suspended the school. Nobody at the school can sign in for now."
              : `The school has left Nex Edu. Its data is kept locked until ${s.purge_after ? formatDate(s.purge_after) : "it is destroyed"}.`}
            {!s.is_owner && " The proprietor has been told what to do."}
          </p>
          {s.is_owner && (
            <Link href={`/account/billing?school=${s.slug}`} className="btn mt-4 h-10">
              {s.status === "suspended" && s.unpaid ? "Pay now" : "Billing and your data"}
            </Link>
          )}
        </section>
      ))}

      {unavailable.length === 0 && (
        <section className="mt-6 rounded-card border border-neutral-200 p-5 dark:border-neutral-800">
          {latest && latest.status !== "rejected" ? (
            <>
              <p className="text-sm text-neutral-500">School registration</p>
              <p className="mt-1 font-medium">
                {latest.school_name}{" "}
                <span className="font-mono text-sm text-neutral-500">
                  ({latest.slug}.{SCHOOL_DOMAIN})
                </span>
              </p>
              <p className="mt-2 inline-flex rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand-strong dark:text-brand-bright">
                {latest.status_label}
              </p>
              <p className="mt-3 text-sm text-neutral-500">
                {latest.status === "pending" || latest.status === "provisioning"
                  ? "We'll email you when it's approved, usually within two working days."
                  : "Our team will be in touch about finishing setup."}
              </p>
            </>
          ) : (
            <>
              <p className="font-medium">You haven't been added to a school yet.</p>
              <p className="mt-1 text-sm text-neutral-500">
                {latest?.status === "rejected"
                  ? `We couldn't approve ${latest.school_name}${latest.decision_note ? `: ${latest.decision_note}` : "."} You can apply again.`
                  : "If your school invited you, use the link in that email. Running a school? Register it here."}
              </p>
              <Link href="/signup" className="btn mt-4 h-10">
                Register a school
              </Link>
            </>
          )}
        </section>
      )}
    </main>
  );
}
