import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import type { ReactNode } from "react";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Nex Edu", template: "%s · Nex Edu" },
  description: "Records, results, fees and communication for your school.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Browser chrome on Android takes the logo's blue in light mode, its navy in dark.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0c63d9" },
    { media: "(prefers-color-scheme: dark)", color: "#042159" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Reading headers makes every page render per request, which a per-request
  // CSP nonce requires.
  await headers();
  return (
    <html lang="en-GB">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
