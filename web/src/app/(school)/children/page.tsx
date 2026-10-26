"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Empty, ErrorText, Loading, PageHeader } from "@/components/ui";
import { api, type Paged, type Student } from "@/lib/api";

export default function ChildrenPage() {
  const children = useQuery({
    queryKey: ["students", "children"],
    queryFn: () => api.get<Paged<Student>>("/api/v1/students"),
  });
  return (
    <>
      <PageHeader title="My children" description="Attendance, results and fees for each child." />
      <ErrorText error={children.error} />
      {children.isPending ? (
        <Loading />
      ) : children.data?.results.length ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {children.data.results.map((c) => (
            <Link
              key={c.id}
              href={`/students/${c.id}`}
              className="rounded-card border border-neutral-200 bg-white p-4 hover:border-brand dark:border-neutral-800 dark:bg-neutral-900"
            >
              <div className="text-lg font-medium">
                {c.first_name} {c.last_name}
              </div>
              <div className="text-sm text-neutral-500">
                {c.arm_name ?? "No class"} · {c.admission_number}
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <Empty>No children are linked to your account yet. Ask the school office to link them.</Empty>
      )}
    </>
  );
}
