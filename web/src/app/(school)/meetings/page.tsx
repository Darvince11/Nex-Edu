"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { hhmm, type MeetingDay, MeetingDayForm } from "@/components/meetings";
import { Badge, Button, Empty, ErrorText, Loading, Modal, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

/** Parent meeting days: leaders set them up, parents book, teachers see their times. */
export default function MeetingsPage() {
  const { can, roles } = useSchool();
  const router = useRouter();
  const manage = can(PERM.MEETINGS_MANAGE);
  const [adding, setAdding] = useState(false);
  const days = useQuery({ queryKey: ["meetings"], queryFn: () => api.get<MeetingDay[]>("/api/v1/meetings") });
  const parent = roles.includes("parent");
  return (
    <>
      <PageHeader
        title="Parent meetings"
        description={
          parent ? "Book a time to see your child's teachers." : "Days when parents come in to see teachers."
        }
        actions={manage && <Button onClick={() => setAdding(true)}>New meeting day</Button>}
      />
      <ErrorText error={days.error} />
      {days.isPending ? (
        <Loading />
      ) : days.data?.length ? (
        <ul className="grid gap-4 sm:grid-cols-2">
          {days.data.map((d) => (
            <li key={d.id}>
              <Link
                href={`/meetings/${d.id}`}
                className="flex h-full flex-col gap-1 rounded-card border border-neutral-200 bg-white p-4 shadow-card hover:border-brand dark:border-neutral-800 dark:bg-neutral-900"
              >
                <span className="font-medium text-brand-strong dark:text-brand-sky">{d.title}</span>
                <span className="text-sm">
                  {formatDate(d.date)}, {hhmm(d.starts_at)} to {hhmm(d.ends_at)}
                  {d.location ? ` · ${d.location}` : ""}
                </span>
                {!parent && (
                  <span className="text-sm text-neutral-600 dark:text-neutral-300">
                    {d.teacher_count} teacher(s) · {d.booked_count} booked
                  </span>
                )}
                <span className="mt-1">
                  {d.is_open ? (
                    <Badge tone="green">Booking open</Badge>
                  ) : (
                    <Badge tone="grey">Not open yet</Badge>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>{parent ? "No meeting days to book at the moment." : "No meeting days yet."}</Empty>
      )}
      <Modal open={adding} onClose={() => setAdding(false)} title="New meeting day">
        {adding && (
          <MeetingDayForm
            day={null}
            onDone={(id) => {
              setAdding(false);
              router.push(`/meetings/${id}`);
            }}
          />
        )}
      </Modal>
    </>
  );
}
