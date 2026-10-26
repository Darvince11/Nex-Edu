"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { PlatformNavItem } from "@/lib/platform";

const CLOSED_GROUPS_KEY = "nexedu.platform.closedGroups";

type Badge = { text: string; label: string } | undefined;

function readClosedGroups(): string[] {
  try {
    return JSON.parse(window.localStorage.getItem(CLOSED_GROUPS_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/**
 * The console menu in groups. On wide screens each group heading has a caret
 * that folds it away; the choice is remembered in this browser, and the group
 * holding the current page always stays open. On phones the menu is one
 * scrolling row with every link, so nothing is folded there.
 */
export function PlatformNav({
  groups,
  pathname,
  badges,
}: {
  groups: { label: string; items: PlatformNavItem[] }[];
  pathname: string;
  badges: Record<NonNullable<PlatformNavItem["badge"]>, Badge>;
}) {
  const [closed, setClosed] = useState<string[]>([]);
  // Read after mount so the server-rendered menu (all open) matches the first client render.
  useEffect(() => setClosed(readClosedGroups()), []);

  function toggle(label: string) {
    const next = closed.includes(label) ? closed.filter((g) => g !== label) : [...closed, label];
    setClosed(next);
    try {
      window.localStorage.setItem(CLOSED_GROUPS_KEY, JSON.stringify(next));
    } catch {
      // Private mode or blocked storage: the choice just isn't remembered.
    }
  }

  const isActive = (item: PlatformNavItem) =>
    pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`));

  return (
    <nav aria-label="Platform" className="-mx-1 overflow-x-auto lg:mx-0 lg:overflow-visible">
      <div className="flex gap-1 px-1 lg:flex-col lg:gap-3 lg:px-0">
        {groups.map((group) => {
          const hasActive = group.items.some(isActive);
          const open = hasActive || !closed.includes(group.label);
          const listId = `platform-nav-${group.label.toLowerCase().replace(/\W+/g, "-")}`;
          return (
            <div key={group.label} className="flex gap-1 lg:flex-col lg:gap-0.5">
              <button
                type="button"
                onClick={() => toggle(group.label)}
                aria-expanded={open}
                aria-controls={listId}
                disabled={hasActive}
                title={hasActive ? "This group holds the page you're on" : undefined}
                className="hidden w-full items-center justify-between rounded px-3 py-1 text-xs font-semibold tracking-wide text-neutral-500 uppercase hover:text-neutral-800 disabled:cursor-default disabled:hover:text-neutral-500 lg:flex dark:hover:text-neutral-200"
              >
                {group.label}
                {!hasActive && (
                  <svg
                    viewBox="0 0 24 24"
                    className={`size-3.5 transition-transform ${open ? "" : "-rotate-90"}`}
                    aria-hidden="true"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                )}
              </button>
              <ul id={listId} className={`flex gap-1 lg:flex-col lg:gap-0.5 ${open ? "" : "lg:hidden"}`}>
                {group.items.map((item) => {
                  const active = isActive(item);
                  const badge = item.badge ? badges[item.badge] : undefined;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        className={`flex shrink-0 items-center justify-between rounded-md px-3 py-2 text-sm whitespace-nowrap ${
                          active
                            ? "bg-brand/10 font-medium text-brand-strong dark:bg-brand/20 dark:text-brand-bright"
                            : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
                        }`}
                      >
                        {item.label}
                        {badge && (
                          <span className="ml-2 rounded-full bg-amber-100 px-1.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                            {badge.text}
                            <span className="sr-only"> {badge.label}</span>
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </nav>
  );
}
