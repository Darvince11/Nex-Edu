"use client";

import { AuditLog } from "@/components/audit-log";
import { PageHeader } from "@/components/ui";

/** The signed-in staff member's own actions and sign-ins. */
export default function MyAuditLogPage() {
  return (
    <>
      <PageHeader title="My audit log" description="What you've done in Nex Edu, including your sign-ins." />
      <AuditLog mine />
    </>
  );
}
