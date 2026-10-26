"use client";

import { ProfilePage } from "@/components/profile";
import { CalendarLinkCard, NotificationsCard } from "@/components/profile-extras";
import { Loading } from "@/components/ui";
import { useSchool } from "@/lib/hooks";
import { ROLE_LABELS, type Role } from "@/lib/roles";

export default function SchoolProfilePage() {
  const { me, school, roles } = useSchool();
  if (!me.data || !school) return <Loading />;
  return (
    <ProfilePage
      me={me.data}
      access={{ label: school.name, roles: roles.map((r) => ROLE_LABELS[r as Role] ?? r) }}
      emailNote="Your school's office can change the email you sign in with."
      extra={
        <>
          <NotificationsCard />
          <CalendarLinkCard />
        </>
      }
      links={
        me.data.platform_roles.length
          ? [
              {
                href: "/platform",
                label: "Nex Edu platform console",
                description: "Review school registrations and see all schools.",
              },
            ]
          : undefined
      }
    />
  );
}
