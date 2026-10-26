"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { locate, type NavGroup, type NavIcon } from "@/lib/nav";

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const PATHS: Record<NavIcon, string[]> = {
  home: ["M3.5 11 12 4l8.5 7", "M5.5 9.5V20h13V9.5", "M10 20v-5h4v5"],
  pupils: ["M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z", "M5 20c.8-3.6 3.6-6 7-6s6.2 2.4 7 6"],
  children: [
    "M8.5 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M16.5 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
    "M3 20c.6-3.2 2.8-5.5 5.5-5.5S13.4 16.8 14 20",
    "M14.5 15.5c2.6-.6 5.3 1 6 4.5",
  ],
  admissions: ["M6 3.5h8l4 4V20.5H6Z", "M14 3.5v4h4", "M9 13h6M12 10v6"],
  people: [
    "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M3.5 19.5c.6-3 2.8-5 5.5-5s4.9 2 5.5 5",
    "M16 5.5a3 3 0 0 1 0 5.5M17.5 14.5c1.7.6 2.7 2.3 3 5",
  ],
  classes: ["M4 5.5h16v11H4Z", "M8 20h8M12 16.5V20"],
  scores: ["M5 4.5h14v15H5Z", "M8.5 9h7M8.5 12.5h7M8.5 16h4"],
  results: ["M7 3.5h10v17H7Z", "m10 12 1.5 1.5L15 10", "M10 7h4"],
  attendance: ["M4.5 6h15v14h-15Z", "M8 3.5v5M16 3.5v5M4.5 10.5h15", "m9 15 2 2 4-4"],
  fees: ["M3.5 7h17v11h-17Z", "M3.5 10.5h17", "M7 14.5h3"],
  announcements: ["M4 10v4h3l7 4V6L7 10H4Z", "M17.5 9a4 4 0 0 1 0 6"],
  inbox: ["M4 5.5h16v13H4Z", "m4.5 6 7.5 6.5L19.5 6"],
  modules: ["M4 4h7v7H4Z", "M13 4h7v7h-7Z", "M4 13h7v7H4Z", "M16.5 13v7M13 16.5h7"],
  staff: [
    "M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
    "M5 20c.8-3.6 3.6-6 7-6s6.2 2.4 7 6",
    "M9.5 14.5 12 17l2.5-2.5",
  ],
  audit: ["M6 3.5h12v17H6Z", "M9 8h6M9 11.5h6M9 15h3", "m14 17 1.5 1.5L18 16"],
  leave: ["M4.5 6h15v14h-15Z", "M8 3.5v5M16 3.5v5M4.5 10.5h15", "M9 15h6"],
  messages: ["M4 5h16v11H9l-5 4Z", "M8 9.5h8M8 12.5h5"],
  library: ["M5 4.5h4v15H5Z", "M9 4.5h4v15H9Z", "m14 5.5 3.8-1 3.7 14.5-3.8 1Z"],
  clubs: ["M12 3.5 14.5 9l6 .5-4.5 4 1.4 6L12 16.4 6.6 19.5 8 13.5l-4.5-4 6-.5Z"],
  meetings: [
    "M8.5 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M15.5 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M3 19c.6-3.2 2.8-5.5 5.5-5.5S13.4 15.8 14 19",
    "M12.5 14.2c.9-.5 1.9-.7 3-.7 2.7 0 4.9 2.3 5.5 5.5",
  ],
  behaviour: ["M12 3.5 19 6v5.5c0 4.2-2.9 7.6-7 9-4.1-1.4-7-4.8-7-9V6Z", "m9 12 2 2 4-4"],
  clinic: ["M4.5 7.5h15v12h-15Z", "M9 7.5V5h6v2.5", "M12 10.5v6M9 13.5h6"],
  transport: ["M5 5.5h14v10.5H5Z", "M5 11h14", "M7.5 19v-3M16.5 19v-3", "M8 13.5h.01M16 13.5h.01"],
  canteen: ["M7 3.5v7a2 2 0 0 0 4 0v-7M9 10.5V20.5", "M16 3.5c-1.7 1-2.5 3-2.5 5.5s.8 3.5 2.5 3.5v8"],
  stores: ["M3.5 9 12 4.5 20.5 9v10.5h-17Z", "M8 19.5v-6h8v6", "M8 16.5h8"],
  facilities: ["M4.5 20V8l7.5-4.5L19.5 8v12", "M9.5 20v-5h5v5", "M3 20h18"],
  gate: ["M4 20V6.5h4V20", "M16 20V6.5h4V20", "M8 9h8M8 13h8", "M3 20h18"],
  homework: ["M5 4.5h11l3 3v12H5Z", "M15.5 4.5v3h3", "M8 11h8M8 14.5h8M8 18h5"],
  boarding: ["M3.5 18.5V8.5", "M3.5 14.5h17v4", "M20.5 14.5V12a3 3 0 0 0-3-3h-6v5.5", "M7 11.5h.01"],
  accounting: [
    "M5 3.5h14v17H5Z",
    "M8 7.5h8",
    "M8 11.5h2M12 11.5h2M8 15h2M12 15h2M8 18.5h2M12 18.5h2",
    "M16 11.5v7",
  ],
  payroll: ["M3.5 7h17v11h-17Z", "M12 15.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M6.5 10v2.5M17.5 10v2.5"],
  procurement: ["M4 5h2l2 10h10l2-7H7", "M9.5 19.5h.01M17 19.5h.01"],
  tests: ["M6 3.5h12v17H6Z", "m9 9 1.5 1.5L13 8", "m9 14.5 1.5 1.5L13 13.5", "M14.5 9.5H16M14.5 15H16"],
  support: ["M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z"],
  integrations: ["M9 7V4M15 7V4", "M7 7h10v4a5 5 0 0 1-10 0Z", "M12 16v4"],
  compliance: ["M12 3.5 5 6.5v5c0 4.3 3 7.6 7 9 4-1.4 7-4.7 7-9v-5Z", "m9 12 2 2 4-4"],
  website: [
    "M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17Z",
    "M3.5 12h17",
    "M12 3.5c2.3 2.4 3.5 5.2 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.2-3.5-8.5s1.2-6.1 3.5-8.5Z",
  ],
  alumni: ["M2.5 9 12 4.5 21.5 9 12 13.5Z", "M6.5 11v4.5c0 1.5 2.5 3 5.5 3s5.5-1.5 5.5-3V11", "M21.5 9v5"],
  reports: ["M4.5 20h15", "M7 16.5V11M11 16.5V6.5M15 16.5v-7M19 16.5V13"],
  calendar: ["M4.5 6h15v14h-15Z", "M8 3.5v5M16 3.5v5M4.5 10.5h15", "M8 14h2M11 14h2M14 14h2M8 17h2"],
  settings: [
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    "M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.3a2 2 0 1 1-4 0v-.2a1.6 1.6 0 0 0-2.7-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.4 14H3a2 2 0 1 1 0-4h.2a1.6 1.6 0 0 0 1.1-2.7l-.1-.1A2 2 0 1 1 7 4.4l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.5 1Z",
  ],
};

export function NavGlyph({ icon, className = "size-5" }: { icon: NavIcon; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`shrink-0 ${className}`} aria-hidden="true" {...stroke}>
      {PATHS[icon].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

const COLLAPSED_GROUPS_KEY = "nexedu.nav.closedGroups";

function readClosedGroups(): string[] {
  try {
    return JSON.parse(window.localStorage.getItem(COLLAPSED_GROUPS_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/**
 * Grouped school navigation. `rail` shows icons only (desktop collapse); groups
 * can be folded, and both choices are remembered in this browser.
 */
export function SchoolNav({
  groups,
  pathname,
  rail = false,
  counts = {},
  onNavigate,
}: {
  groups: NavGroup[];
  pathname: string;
  rail?: boolean;
  /** Small badges by link, e.g. unread messages for /inbox. */
  counts?: Record<string, number>;
  onNavigate?: () => void;
}) {
  const [closed, setClosed] = useState<string[]>([]);
  // Loaded after mount so the server-rendered menu (all open) matches the first client render.
  useEffect(() => setClosed(readClosedGroups()), []);

  function toggle(id: string) {
    const next = closed.includes(id) ? closed.filter((g) => g !== id) : [...closed, id];
    setClosed(next);
    try {
      window.localStorage.setItem(COLLAPSED_GROUPS_KEY, JSON.stringify(next));
    } catch {
      // Private mode or blocked storage: the choice just isn't remembered.
    }
  }

  const current = locate(groups, pathname)?.item.href;

  return (
    <nav aria-label="School" className="flex flex-col gap-3">
      {groups.map((group) => {
        const hasActive = group.items.some((item) => item.href === current);
        // A group holding the current page always stays open.
        const open = rail || hasActive || !closed.includes(group.id);
        const listId = `nav-group-${group.id}`;
        return (
          <div
            key={group.id}
            className={
              rail
                ? "border-t border-neutral-200 pt-3 first:border-t-0 first:pt-0 dark:border-neutral-800"
                : ""
            }
          >
            {!rail && (
              <button
                type="button"
                onClick={() => toggle(group.id)}
                aria-expanded={open}
                aria-controls={listId}
                disabled={hasActive}
                className="mb-1 flex w-full items-center justify-between rounded px-3 py-1 text-xs font-semibold tracking-wide text-neutral-500 uppercase hover:text-neutral-800 disabled:cursor-default disabled:hover:text-neutral-500 dark:hover:text-neutral-200"
              >
                {group.label}
                {!hasActive && (
                  <svg
                    viewBox="0 0 24 24"
                    className={`size-3.5 transition-transform ${open ? "" : "-rotate-90"}`}
                    aria-hidden="true"
                    {...stroke}
                  >
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                )}
              </button>
            )}
            {open && (
              <ul id={listId} className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const active = item.href === current;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        title={rail ? item.label : undefined}
                        className={`relative flex items-center gap-3 rounded-control py-2 text-sm ${rail ? "justify-center px-2" : "px-3"} ${
                          active
                            ? "bg-brand/10 font-medium text-brand-strong dark:bg-brand/20 dark:text-brand-bright"
                            : "text-neutral-700 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800"
                        }`}
                      >
                        <NavGlyph icon={item.icon} className={rail ? "size-5" : "size-[1.125rem]"} />
                        <span className={rail ? "sr-only" : "flex-1"}>{item.label}</span>
                        {Boolean(counts[item.href]) &&
                          (rail ? (
                            <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-brand">
                              <span className="sr-only">{counts[item.href]} unread</span>
                            </span>
                          ) : (
                            <span className="rounded-full bg-brand px-1.5 text-xs font-medium text-white">
                              {counts[item.href]}
                              <span className="sr-only"> unread</span>
                            </span>
                          ))}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </nav>
  );
}
