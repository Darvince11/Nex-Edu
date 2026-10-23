"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ApplicationForm } from "@/components/application-form";
import { LogoMark } from "@/components/brand";
import { Alert, Loading } from "@/components/ui";
import { apiFetch } from "@/lib/api";

export default function ApplyPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Apply />
    </Suspense>
  );
}

/**
 * Public online admission form. In production the school comes from the
 * subdomain (greenfield.nexedu.com.gh/apply); locally use /apply?school=greenfield.
 */
function Apply() {
  const school = useSearchParams().get("school") ?? undefined;
  const [reference, setReference] = useState<string | null>(null);
  const options = useQuery({
    queryKey: ["public-admissions", school],
    queryFn: () =>
      apiFetch<{ school: string; levels: { id: number; name: string }[] }>("/api/v1/public/admissions", {
        school,
      }),
  });

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold">
        {options.data ? `Apply to ${options.data.school}` : "School admission"}
      </h1>
      <p className="mt-1 mb-6 text-sm text-neutral-500">
        Fill in the form and the school will contact you on the phone number you give.
      </p>
      {options.isPending && <Loading />}
      {options.error && (
        <Alert tone="error">We couldn't find this school. Check the link and try again.</Alert>
      )}
      {reference ? (
        <Alert tone="success">
          Application received. Your reference is <strong>{reference}</strong>. Keep it for any enquiries.
        </Alert>
      ) : (
        options.data && (
          <ApplicationForm
            levels={options.data.levels}
            submit={(body) =>
              apiFetch<{ reference: string }>("/api/v1/public/admissions", { method: "POST", body, school })
            }
            onDone={(ref) => setReference(ref ?? "received")}
          />
        )
      )}
      <footer className="mt-10 flex items-center justify-center gap-2 text-xs text-neutral-500">
        <LogoMark className="h-6" alt="" />
        Powered by Nex Edu
      </footer>
    </main>
  );
}
