"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ApiError, apiFetch, type Me, selectSchool } from "@/lib/api";

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

  useEffect(() => {
    if (me.error instanceof ApiError && [401, 403].includes(me.error.status)) {
      router.replace("/login");
    }
  }, [me.error, router]);

  if (me.isPending) return <p className="p-6">Loading…</p>;
  if (!me.data) return <p className="p-6">Could not load your account.</p>;

  function open(slug: string) {
    selectSchool(slug);
    router.push("/dashboard");
  }

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <h1 className="text-2xl font-semibold">Choose a school</h1>
      <p className="mt-1 text-neutral-500">Signed in as {me.data.email}</p>

      {!me.data.mfa_enrolled && (
        <p className="mt-6 rounded-md bg-amber-50 p-3 text-sm text-amber-900">
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
              className="w-full rounded-lg border border-neutral-200 p-4 text-left hover:border-brand dark:border-neutral-800"
            >
              <span className="block font-medium">{school.name}</span>
              <span className="text-sm text-neutral-500">
                {school.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}
              </span>
            </button>
          </li>
        ))}
        {me.data.schools.length === 0 && (
          <li className="text-neutral-500">You haven't been added to a school yet.</li>
        )}
      </ul>
    </main>
  );
}
