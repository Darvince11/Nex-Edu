"use client";

import { useEffect, useState } from "react";
import { applyTheme, currentTheme, THEME_EVENT, THEME_KEY, type Theme } from "@/lib/theme";

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

/** The current theme, kept in step with other toggles on the page and other tabs. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    setTheme(currentTheme());
    const onChange = () => setTheme(currentTheme());
    const onStorage = (e: StorageEvent) => {
      if (e.key !== THEME_KEY) return;
      document.documentElement.classList.toggle("dark", e.newValue === "dark");
      onChange();
    };
    window.addEventListener(THEME_EVENT, onChange);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(THEME_EVENT, onChange);
      window.removeEventListener("storage", onStorage);
    };
  }, []);
  return [theme, applyTheme];
}

/** Switches between light and dark mode. */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={next === "dark" ? "Switch to dark mode" : "Switch to light mode"}
      title={next === "dark" ? "Dark mode" : "Light mode"}
      className={`grid size-9 shrink-0 place-items-center rounded-control text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 dark:text-neutral-300 dark:hover:bg-neutral-800 dark:hover:text-neutral-100 ${className}`}
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true" {...stroke}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true" {...stroke}>
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
        </svg>
      )}
    </button>
  );
}
