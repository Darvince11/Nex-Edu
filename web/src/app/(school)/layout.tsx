"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import { Logo, LogoMark } from "@/components/brand";
import { logout } from "@/lib/allauth";
import { ApiError, api } from "@/lib/api";
import { loginPath } from "@/lib/auth";
import { useSchool } from "@/lib/hooks";
import { navFor, ROLE_LABELS, type Role } from "@/lib/roles";

export default function SchoolLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { me, slug, school, roles } = useSchool();

  useEffect(() => {
    if (me.error instanceof ApiError && [401, 403].includes(me.error.status))
      router.replace(loginPath(me.error.code));
    else if (slug === undefined || (me.data && slug && !school)) router.replace("/schools");
  }, [me.error, me.data, slug, school, router]);

  const unread = useQuery({
    queryKey: ["unread"],
    queryFn: () => api.get<{ unread: number }>("/api/v1/communication/notifications/unread_count"),
    enabled: Boolean(school),
    refetchInterval: 60_000,
  });

  if (!school) return <p className="p-6 text-sm text-neutral-500">Loading…</p>;

  const nav = navFor(roles);
  const signOut = async () => {
    await logout();
    router.replace("/login");
  };

  const links = (
    <nav className="flex flex-col gap-0.5">
      {nav.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded-md px-3 py-2 text-sm ${
              active
                ? "bg-brand/10 font-medium text-brand-strong dark:bg-brand/20 dark:text-brand-bright"
                : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="hidden border-r border-neutral-200 bg-white p-4 lg:block dark:border-neutral-800 dark:bg-neutral-950">
        <Link href="/dashboard" className="mb-3 block" aria-label="Nex Edu dashboard">
          <Logo className="h-11" />
        </Link>
        <p className="mb-4 text-xs text-neutral-500">{school.name}</p>
        {links}
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-neutral-200 bg-white px-4 py-3 dark:border-neutral-800 dark:bg-neutral-950">
          <div className="flex shrink-0 items-center gap-2 lg:hidden">
            <Link href="/dashboard" aria-label="Nex Edu dashboard">
              <LogoMark className="h-8" />
            </Link>
            <details className="relative">
              <summary className="cursor-pointer list-none rounded-md border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-700">
                Menu
              </summary>
              <div className="absolute z-20 mt-2 w-64 rounded-lg border border-neutral-200 bg-white p-2 shadow-lg dark:border-neutral-800 dark:bg-neutral-900">
                {links}
              </div>
            </details>
          </div>
          <div className="min-w-0 text-sm">
            <span className="font-medium">{school.name}</span>
            <span className="hidden text-neutral-500 sm:inline">
              {" "}
              · {roles.map((r) => ROLE_LABELS[r as Role] ?? r).join(", ")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/inbox"
              className="relative rounded-md px-3 py-1.5 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
            >
              Inbox
              {Boolean(unread.data?.unread) && (
                <span className="ml-1 rounded-full bg-brand px-1.5 text-xs text-white">
                  {unread.data?.unread}
                </span>
              )}
            </Link>
            <Link
              href="/schools"
              className="hidden rounded-md px-3 py-1.5 text-sm hover:bg-neutral-100 sm:inline dark:hover:bg-neutral-800"
            >
              Switch school
            </Link>
            <button
              type="button"
              onClick={signOut}
              className="rounded-md px-3 py-1.5 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
            >
              Sign out
            </button>
          </div>
        </header>
        {!me.data?.mfa_enrolled && !roles.every((r) => r === "parent" || r === "student") && (
          <div className="bg-amber-50 px-4 py-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
            Staff accounts need a passkey or authenticator app before they can see school records.{" "}
            <Link href="/security" className="font-medium underline">
              Set one up
            </Link>
          </div>
        )}
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      </div>
    </div>
  );
}
