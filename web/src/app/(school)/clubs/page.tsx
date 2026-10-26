"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { type Activity, type Club, ClubForm } from "@/components/clubs";
import { Badge, Button, Empty, ErrorText, Loading, Modal, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

/** Clubs, societies and teams; leaders set them up, patrons run them. */
export default function ClubsPage() {
  const { can, roles } = useSchool();
  const manage = can(PERM.CLUBS_MANAGE);
  const family = roles.includes("parent") || roles.includes("student");
  const [adding, setAdding] = useState(false);
  const clubs = useQuery({ queryKey: ["clubs"], queryFn: () => api.get<Club[]>("/api/v1/clubs") });
  const coming = useQuery({
    queryKey: ["club-activities", "mine"],
    queryFn: () => api.get<Activity[]>("/api/v1/clubs/activities?mine=1&upcoming=1"),
  });

  return (
    <>
      <PageHeader
        title="Clubs and sports"
        description="Clubs, societies and teams, who runs them, and what's coming up."
        actions={manage && <Button onClick={() => setAdding(true)}>New club</Button>}
      />
      {(coming.data?.length ?? 0) > 0 && (
        <section aria-labelledby="coming-title" className="mb-6">
          <h2 id="coming-title" className="mb-2 font-medium">
            {family ? "Coming up for your family" : "Coming up in your clubs"}
          </h2>
          <ul className="divide-y divide-neutral-100 rounded-card border border-neutral-200 bg-white text-sm dark:divide-neutral-800 dark:border-neutral-800 dark:bg-neutral-900">
            {coming.data?.slice(0, 8).map((a) => (
              <li key={a.id} className="flex flex-wrap justify-between gap-2 px-4 py-2">
                <span>
                  <span className="font-medium">{a.title}</span> · {a.club_name}
                  {a.opponent ? ` vs ${a.opponent}` : ""}
                </span>
                <span className="text-neutral-600 dark:text-neutral-300">
                  {formatDate(a.date)}
                  {a.starts_at ? `, ${a.starts_at.slice(0, 5)}` : ""}
                  {a.venue ? ` · ${a.venue}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <ErrorText error={clubs.error} />
      {clubs.isPending ? (
        <Loading />
      ) : clubs.data?.length ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {clubs.data.map((c) => (
            <li key={c.id}>
              <Link
                href={`/clubs/${c.id}`}
                className="flex h-full flex-col gap-1 rounded-card border border-neutral-200 bg-white p-4 shadow-card hover:border-brand dark:border-neutral-800 dark:bg-neutral-900"
              >
                <span className="font-medium text-brand-strong dark:text-brand-sky">{c.name}</span>
                <span className="text-sm text-neutral-600 dark:text-neutral-300">{c.kind_label}</span>
                {c.meets && <span className="text-sm">{c.meets}</span>}
                <span className="text-sm text-neutral-600 dark:text-neutral-300">
                  {c.member_count}
                  {c.capacity ? ` of ${c.capacity}` : ""} members
                  {c.patrons.length ? ` · Patron: ${c.patrons.map((p) => p.name).join(", ")}` : ""}
                </span>
                <span className="mt-1 flex flex-wrap gap-1">
                  {c.i_run && <Badge tone="blue">You run this</Badge>}
                  {c.my_children.map((name) => (
                    <Badge key={name} tone="green">{`${name} is a member`}</Badge>
                  ))}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>{manage ? "No clubs yet. Add the first one." : "No clubs yet."}</Empty>
      )}
      <Modal open={adding} onClose={() => setAdding(false)} title="New club">
        {adding && <ClubForm club={null} onDone={() => setAdding(false)} />}
      </Modal>
    </>
  );
}
