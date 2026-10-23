"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Logo } from "@/components/brand";
import { logout } from "@/lib/allauth";
import { ApiError, apiFetch, type Me, type Registration, selectSchool } from "@/lib/api";
import { loginPath, SCHOOL_DOMAIN } from "@/lib/auth";

const ROLE_LABELS: Record<string, string> = {
  owner: "Proprietor",
  principal: "Principal",
  admin: "Administrator",
  bursar: "Bursar",
  teacher: "Teacher",
  form_teacher: "Form teacher",
  librarian: "Librarian",
  warden: "Hostel warden",
  driver: "Driver",
  parent: "Parent",
  student: "Student",
};

export default function SchoolsPage() {
  const router = useRouter();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }),
  });
  const noSchools = me.data?.schools.length === 0;
  const registrations = useQuery({
    queryKey: ["registrations"],
    queryFn: () => apiFetch<Registration[]>("/api/v1/registrations", { school: false }),
    enabled: noSchools,
  });

  useEffect(() => {
    if (me.error instanceof ApiError && [401, 403].includes(me.error.status)) {
      router.replace(loginPath(me.error.code));
    }
  }, [me.error, router]);

  if (me.isPending) return <p className="p-6">Loading…</p>;
  if (!me.data) return <p className="p-6">Could not load your account.</p>;

  function open(slug: string) {
    selectSchool(slug);
    router.push("/dashboard");
  }

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  const isStaff = me.data.schools.some((s) => s.roles.some((r) => r !== "parent" && r !== "student"));
  const latest = registrations.data?.[0];

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <div className="mb-8 flex items-center justify-between gap-4">
        <Logo className="h-12" />
        <button
          type="button"
          onClick={signOut}
          className="text-sm font-medium text-neutral-500 hover:text-brand"
        >
          Sign out
        </button>
      </div>
      <h1 className="text-2xl font-semibold">{noSchools ? "Your account" : "Choose a school"}</h1>
      <p className="mt-1 text-neutral-500">Signed in as {me.data.email}</p>

      {isStaff && !me.data.mfa_enrolled && (
        <p className="mt-6 rounded-md bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
          Staff accounts need a passkey or authenticator app.{" "}
          <Link href="/security" className="font-medium underline">
            Set one up
          </Link>
          .
        </p>
      )}

      <ul className="mt-6 flex flex-col gap-3">
        {me.data.schools.map((school) => (
          <li key={school.slug}>
            <button
              type="button"
              onClick={() => open(school.slug)}
              className="w-full rounded-lg border border-neutral-200 p-4 text-left hover:border-brand hover:bg-brand/5 dark:border-neutral-800"
            >
              <span className="block font-medium">{school.name}</span>
              <span className="text-sm text-neutral-500">
                {school.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {noSchools && (
        <section className="mt-2 rounded-xl border border-neutral-200 p-5 dark:border-neutral-800">
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
                {latest.status === "pending"
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
