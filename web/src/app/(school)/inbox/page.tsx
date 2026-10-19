"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Empty, ErrorText, Loading, PageHeader } from "@/components/ui";
import { api, type Notification, type Paged } from "@/lib/api";
import { formatDate } from "@/lib/format";

export default function InboxPage() {
  const client = useQueryClient();
  const items = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<Paged<Notification>>("/api/v1/communication/notifications?page_size=100"),
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["notifications"] });
    client.invalidateQueries({ queryKey: ["unread"] });
  };
  const readAll = useMutation({
    mutationFn: () => api.post("/api/v1/communication/notifications/read_all"),
    onSuccess: refresh,
  });
  const read = useMutation({
    mutationFn: (id: string) => api.post(`/api/v1/communication/notifications/${id}/read`),
    onSuccess: refresh,
  });

  return (
    <>
      <PageHeader
        title="Inbox"
        actions={
          <Button variant="secondary" busy={readAll.isPending} onClick={() => readAll.mutate()}>
            Mark all as read
          </Button>
        }
      />
      <ErrorText error={items.error} />
      {items.isPending ? (
        <Loading />
      ) : items.data?.results.length ? (
        <ul className="divide-y divide-neutral-100 rounded-xl border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
          {items.data.results.map((n) => (
            <li
              key={n.id}
              className={`flex items-start justify-between gap-3 px-4 py-3 ${n.read_at ? "" : "bg-emerald-50/60 dark:bg-emerald-950/30"}`}
            >
              <div>
                <div className="font-medium">{n.title}</div>
                <div className="text-sm text-neutral-600 dark:text-neutral-400">{n.body}</div>
                <div className="text-xs text-neutral-500">{formatDate(n.created_at)}</div>
              </div>
              {!n.read_at && (
                <Button variant="ghost" onClick={() => read.mutate(n.id)}>
                  Mark read
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <Empty>Nothing here yet.</Empty>
      )}
    </>
  );
}
