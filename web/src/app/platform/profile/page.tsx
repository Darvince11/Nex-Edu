"use client";

import { useQuery } from "@tanstack/react-query";
import { ProfilePage } from "@/components/profile";
import { Loading } from "@/components/ui";
import { apiFetch, type Me } from "@/lib/api";
import { PLATFORM_ROLE_LABELS } from "@/lib/roles";

export default function PlatformProfilePage() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/v1/me", { school: false }),
  });
  if (!me.data) return <Loading />;
  return (
    <ProfilePage
      me={me.data}
      access={{
        label: "Nex Edu platform",
        roles: me.data.platform_roles.map((r) => PLATFORM_ROLE_LABELS[r] ?? r),
      }}
      emailNote="Ask a super admin to change the email you sign in with."
      links={
        me.data.schools.length
          ? [{ href: "/schools", label: "Go to your school", description: "Open your school's workspace." }]
          : undefined
      }
    />
  );
}
