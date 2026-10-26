"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LogoMark } from "@/components/brand";
import { apiFetch, type NexEduAnnouncement } from "@/lib/api";
import { formatDate } from "@/lib/format";

/** News from Nex Edu for proprietors, shown until they dismiss it. Others get none. */
export function NexEduAnnouncements() {
  const client = useQueryClient();
  const items = useQuery({
    queryKey: ["nexedu-announcements"],
    queryFn: () => apiFetch<NexEduAnnouncement[]>("/api/v1/nexedu-announcements", { school: false }),
    staleTime: 5 * 60_000,
  });
  const dismiss = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/v1/nexedu-announcements/${id}/read`, { method: "POST", school: false }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["nexedu-announcements"] }),
  });
  if (!items.data?.length) return null;
  return (
    <div className="grid gap-2 border-b border-brand/20 bg-brand-50 px-4 py-3 dark:border-brand/30 dark:bg-brand/10">
      {items.data.map((a) => (
        <section key={a.id} aria-label={`From Nex Edu: ${a.title}`} className="flex gap-3 text-sm">
          <LogoMark className="mt-0.5 h-6 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">
              {a.title}{" "}
              <span className="text-xs font-normal text-neutral-600 dark:text-neutral-300">
                · From Nex Edu, {formatDate(a.published_at)}
              </span>
            </p>
            <p className="mt-0.5 whitespace-pre-line text-neutral-700 dark:text-neutral-200">{a.body}</p>
          </div>
          <button
            type="button"
            onClick={() => dismiss.mutate(a.id)}
            className="h-fit shrink-0 rounded-control px-2 py-1 text-neutral-600 hover:bg-white hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-neutral-100"
          >
            Dismiss
          </button>
        </section>
      ))}
    </div>
  );
}
