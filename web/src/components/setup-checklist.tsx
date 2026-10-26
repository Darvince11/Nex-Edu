"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Meter } from "@/components/charts";
import { Button, ErrorText } from "@/components/ui";
import { api } from "@/lib/api";

export type SetupChecklist = {
  steps: {
    key: string;
    label: string;
    description: string;
    href: string;
    done: boolean;
    can_do: boolean;
    who: string;
  }[];
  done: number;
  total: number;
  complete: boolean;
  hidden: boolean;
  terms_version: string;
  terms_accepted_by: string;
  terms_accepted_at: string | null;
};

const PATH = "/api/v1/school/setup";

export function useSetupChecklist(enabled: boolean) {
  return useQuery({
    queryKey: ["school-setup"],
    queryFn: () => api.get<SetupChecklist>(PATH),
    enabled,
  });
}

export function useSetupAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: "accept_terms" | "hide" | "show") => api.post<SetupChecklist>(PATH, { action }),
    onSuccess: (data) => client.setQueryData(["school-setup"], data),
  });
}

function Tick({ done }: { done: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-[11px] ${
        done ? "bg-emerald-600 text-white" : "border border-neutral-300 dark:border-neutral-600"
      }`}
    >
      {done ? "✓" : ""}
    </span>
  );
}

/**
 * The new-school checklist on the dashboard. Steps tick themselves off when the
 * work is done anywhere in the app; steps the viewer can't do say who can.
 */
export function SetupChecklistCard() {
  const checklist = useSetupChecklist(true);
  const act = useSetupAction();
  if (!checklist.data || checklist.data.hidden || checklist.data.complete) return null;
  const c = checklist.data;
  const next = c.steps.find((s) => !s.done && s.can_do);

  return (
    <section
      aria-labelledby="setup-heading"
      className="mb-6 rounded-card border border-brand/30 bg-white p-4 shadow-card dark:bg-neutral-900"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="setup-heading" className="font-medium">
            Get your school ready
          </h2>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            {c.done} of {c.total} steps done. Each one ticks itself off when it's finished.
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => act.mutate("hide")}
          busy={act.isPending && act.variables === "hide"}
        >
          Hide checklist
        </Button>
      </div>
      <div className="mt-3">
        <Meter value={c.done} max={c.total} label="Set-up steps done" />
      </div>
      <ErrorText error={act.error} />
      <ol className="mt-4 grid gap-2 md:grid-cols-2">
        {c.steps.map((step) => (
          <li
            key={step.key}
            className={`flex gap-3 rounded-control border p-3 text-sm ${
              step.key === next?.key
                ? "border-brand/50 bg-brand/5 dark:bg-brand/10"
                : "border-neutral-200 dark:border-neutral-800"
            }`}
          >
            <Tick done={step.done} />
            <div className="min-w-0 flex-1">
              <p className={`font-medium ${step.done ? "text-neutral-500 line-through" : ""}`}>
                <span className="sr-only">{step.done ? "Done: " : "To do: "}</span>
                {step.label}
              </p>
              {!step.done && (
                <>
                  <p className="text-xs text-neutral-600 dark:text-neutral-300">{step.description}</p>
                  {step.can_do ? (
                    step.key === "terms" ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Button
                          onClick={() => act.mutate("accept_terms")}
                          busy={act.isPending && act.variables === "accept_terms"}
                        >
                          Accept for the school
                        </Button>
                        <span className="text-xs text-neutral-500">
                          Read the{" "}
                          <Link href="/legal/terms" className="text-link underline" target="_blank">
                            terms
                          </Link>{" "}
                          and{" "}
                          <Link href="/legal/privacy" className="text-link underline" target="_blank">
                            privacy notice
                          </Link>
                          .
                        </span>
                      </div>
                    ) : (
                      <Link
                        href={step.href}
                        className="mt-1 inline-block text-xs font-medium text-link underline hover:text-link-hover"
                      >
                        {step.key === next?.key ? "Do this next" : "Go there"}
                        <span className="sr-only">: {step.label}</span>
                      </Link>
                    )
                  ) : (
                    <p className="mt-1 text-xs text-neutral-500">Done by: {step.who}</p>
                  )}
                </>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
