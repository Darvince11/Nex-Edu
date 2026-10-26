"use client";

import { AuditLog } from "@/components/audit-log";
import { PageHeader } from "@/components/ui";

/** Every recorded Nex Edu action and security event, filed by school. */
export default function GeneralAuditLogPage() {
  return (
    <>
      <PageHeader
        title="General audit log"
        description="Everything Nex Edu staff did and every sign-in event, filed under the school it concerns. Entries can't be edited or deleted."
      />
      <AuditLog />
    </>
  );
}
