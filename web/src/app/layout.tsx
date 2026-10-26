import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";
import { THEME_SCRIPT } from "@/lib/theme";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Nex Edu", template: "%s · Nex Edu" },
  description: "Records, results, fees and communication for your school.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Browser chrome on Android takes the logo's blue.
  themeColor: "#0c63d9",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Reading headers makes every page render per request, which a per-request
  // CSP nonce requires.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    // The theme script may add class="dark" before React hydrates.
    <html lang="en-GB" suppressHydrationWarning>
      <head>
        {/* biome-ignore lint/security/noDangerouslySetInnerHtml: a fixed, nonce-allowed script; no user input. */}
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
