"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { listenForErrors } from "@/lib/error-reporting";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            // Auth and permission errors won't fix themselves on retry.
            retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
          },
        },
      }),
  );
  useEffect(() => listenForErrors(), []);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
