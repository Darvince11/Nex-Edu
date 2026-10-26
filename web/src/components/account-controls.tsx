"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";
import { logout } from "@/lib/allauth";
import type { Me } from "@/lib/api";

export function initials(me: Pick<Me, "first_name" | "last_name" | "email">): string {
  const fromName = `${me.first_name.trim().charAt(0)}${me.last_name.trim().charAt(0)}`;
  return (fromName || me.email.charAt(0)).toUpperCase();
}

/** Top-right of every signed-in screen: theme, the person's profile, and sign out. */
export function AccountControls({ me, profileHref }: { me: Me; profileHref: string }) {
  const router = useRouter();
  const name = `${me.first_name} ${me.last_name}`.trim() || me.email;

  async function signOut() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="flex items-center gap-1.5">
      <ThemeToggle />
      <Link
        href={profileHref}
        aria-label={`Your profile (${name})`}
        className="flex items-center gap-2 rounded-control py-1 pr-2 pl-1 hover:bg-neutral-100 dark:hover:bg-neutral-800"
      >
        <span
          aria-hidden="true"
          className="grid size-8 place-items-center rounded-full bg-brand text-xs font-semibold text-white"
        >
          {initials(me)}
        </span>
        <span className="hidden max-w-40 truncate text-sm font-medium sm:inline">{name}</span>
      </Link>
      <button
        type="button"
        onClick={signOut}
        className="rounded-control border border-neutral-300 px-3 py-1.5 text-sm font-medium hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800"
      >
        Sign out
      </button>
    </div>
  );
}
