import type { ReactNode } from "react";
import { MarketingShell } from "@/components/marketing";

export default function MarketingLayout({ children }: { children: ReactNode }) {
  return <MarketingShell>{children}</MarketingShell>;
}
