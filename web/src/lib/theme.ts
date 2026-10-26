/**
 * Light or dark. Light is the default; the person's choice is remembered in this
 * browser. The class goes on <html> before the page paints (THEME_SCRIPT in the
 * root layout), so dark mode never flashes white.
 */
export type Theme = "light" | "dark";

export const THEME_KEY = "nexedu.theme";
/** Fired on window when the theme changes, so every toggle on the page agrees. */
export const THEME_EVENT = "nexedu:theme";

/** Runs in <head> before paint. Kept tiny and dependency-free. */
export const THEME_SCRIPT = `try{if(localStorage.getItem("${THEME_KEY}")==="dark")document.documentElement.classList.add("dark")}catch(e){}`;

export function currentTheme(): Theme {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark")
    ? "dark"
    : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage blocked (private mode): the choice lasts for this page only.
  }
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }));
}
