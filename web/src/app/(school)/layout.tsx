"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { AccountControls } from "@/components/account-controls";
import { Logo, LogoMark } from "@/components/brand";
import { NexEduAnnouncements } from "@/components/nexedu-announcements";
import { SchoolNav } from "@/components/sidebar";
import { ApiError, api } from "@/lib/api";
import { loginPath } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { SCHOOL_LOGO, SchoolContext, useResolveSchool, useSchoolLogo } from "@/lib/hooks";
import { locate, navFor } from "@/lib/nav";
import { PERM } from "@/lib/permissions";
import { isLeader, ROLE_LABELS, type Role } from "@/lib/roles";

const RAIL_KEY = "nexedu.nav.rail";

export default function SchoolLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useResolveSchool();
  const { me, school, roles, permissions } = session;
  const [rail, setRail] = useState(false);
  const mobileMenu = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    if (me.error instanceof ApiError && [401, 403].includes(me.error.status))
      router.replace(loginPath(me.error.code));
    // No school at all (yet): /schools shows their registration or invitation status.
    else if (me.data && me.data.schools.length === 0) router.replace("/schools");
  }, [me.error, me.data, router]);

  useEffect(() => {
    try {
      setRail(window.localStorage.getItem(RAIL_KEY) === "1");
    } catch {
      // Storage blocked: start expanded.
    }
  }, []);

  const schoolLogo = useSchoolLogo(SCHOOL_LOGO, school?.slug);

  const unread = useQuery({
    queryKey: ["unread"],
    queryFn: () => api.get<{ unread: number }>("/api/v1/communication/notifications/unread_count"),
    enabled: Boolean(school),
    refetchInterval: 60_000,
  });
  const unreadMessages = useQuery({
    queryKey: ["messages-unread"],
    queryFn: () => api.get<{ unread: number }>("/api/v1/communication/conversations/unread_count"),
    enabled: Boolean(school) && permissions.includes(PERM.MESSAGES_USE),
    refetchInterval: 60_000,
  });

  if (!school) return <p className="p-6 text-sm text-neutral-500">Loading…</p>;

  const groups = navFor(roles, permissions, school.modules, school.custom_permissions);
  const counts = { "/inbox": unread.data?.unread ?? 0, "/messages": unreadMessages.data?.unread ?? 0 };
  const here = locate(groups, pathname);
  const toggleRail = () => {
    const next = !rail;
    setRail(next);
    try {
      window.localStorage.setItem(RAIL_KEY, next ? "1" : "0");
    } catch {
      // Not remembered; fine.
    }
  };

  return (
    <SchoolContext value={session}>
      <div className={`min-h-dvh lg:grid ${rail ? "lg:grid-cols-[4.5rem_1fr]" : "lg:grid-cols-[15rem_1fr]"}`}>
        <aside
          className={`sticky top-0 hidden h-dvh flex-col border-r border-neutral-200 bg-white py-4 lg:flex dark:border-neutral-800 dark:bg-neutral-950 ${rail ? "px-2" : "px-4"}`}
        >
          <Link
            href="/dashboard"
            className={`mb-1 block ${rail ? "mx-auto" : ""}`}
            aria-label="Nex Edu dashboard"
          >
            {rail ? <LogoMark className="h-9" /> : <Logo className="h-11" />}
          </Link>
          {!rail && <p className="mb-4 truncate text-xs text-neutral-500">{school.name}</p>}
          <div className={`min-h-0 flex-1 overflow-y-auto ${rail ? "mt-4" : ""}`}>
            <SchoolNav groups={groups} pathname={pathname} rail={rail} counts={counts} />
          </div>
          <button
            type="button"
            onClick={toggleRail}
            aria-label={rail ? "Expand menu" : "Collapse menu"}
            title={rail ? "Expand menu" : "Collapse menu"}
            className={`mt-3 flex items-center gap-2 rounded-md py-2 text-sm text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800 dark:hover:bg-neutral-800 dark:hover:text-neutral-200 ${rail ? "justify-center px-2" : "px-3"}`}
          >
            <svg
              viewBox="0 0 24 24"
              className={`size-5 transition-transform ${rail ? "rotate-180" : ""}`}
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 5v14M20 12H9m4-4-4 4 4 4" />
            </svg>
            {!rail && "Collapse menu"}
          </button>
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-white px-4 py-3 dark:border-neutral-800 dark:bg-neutral-950">
            <div className="flex shrink-0 items-center gap-2 lg:hidden">
              <Link href="/dashboard" aria-label="Nex Edu dashboard">
                <LogoMark className="h-8" />
              </Link>
              <details ref={mobileMenu} className="relative">
                <summary className="cursor-pointer list-none rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700">
                  Menu
                </summary>
                <div className="absolute z-20 mt-2 max-h-[75dvh] w-72 overflow-y-auto rounded-lg border border-neutral-200 bg-white p-3 shadow-lg dark:border-neutral-800 dark:bg-neutral-900">
                  <SchoolNav
                    groups={groups}
                    pathname={pathname}
                    counts={counts}
                    onNavigate={() => mobileMenu.current?.removeAttribute("open")}
                  />
                </div>
              </details>
            </div>
            <div className="flex min-w-0 items-center gap-2 text-sm">
              {schoolLogo && (
                // biome-ignore lint/performance/noImgElement: a local blob URL; next/image can't optimise it.
                <img src={schoolLogo} alt="" className="size-7 shrink-0 rounded object-contain" />
              )}
              <span className="truncate font-medium">{school.name}</span>
              <span className="hidden text-neutral-500 sm:inline">
                {" "}
                · {roles.map((r) => ROLE_LABELS[r as Role] ?? r).join(", ")}
              </span>
            </div>
            {me.data && <AccountControls me={me.data} profileHref="/profile" />}
          </header>
          <NexEduAnnouncements />
          {school.support_access_until && isLeader(roles) && (
            <p role="status" className="bg-brand/10 px-4 py-2 text-center text-sm">
              Nex Edu support can see how this school is set up (never pupils' records) until{" "}
              {formatDate(school.support_access_until)}.{" "}
              {roles.includes("owner") && (
                <Link href="/subscription" className="font-medium text-link underline">
                  Manage
                </Link>
              )}
            </p>
          )}
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
            {here && here.group.id !== "dashboard" && (
              <nav aria-label="Breadcrumb" className="mb-3 text-sm text-neutral-500">
                <ol className="flex flex-wrap items-center gap-1.5">
                  <li>{here.group.label}</li>
                  <li aria-hidden="true">›</li>
                  {pathname === here.item.href ? (
                    <li aria-current="page" className="font-medium text-neutral-800 dark:text-neutral-200">
                      {here.item.label}
                    </li>
                  ) : (
                    <>
                      <li>
                        <Link href={here.item.href} className="text-link hover:text-link-hover">
                          {here.item.label}
                        </Link>
                      </li>
                      <li aria-hidden="true">›</li>
                      <li aria-current="page" className="font-medium text-neutral-800 dark:text-neutral-200">
                        Details
                      </li>
                    </>
                  )}
                </ol>
              </nav>
            )}
            {children}
          </main>
        </div>
      </div>
    </SchoolContext>
  );
}
