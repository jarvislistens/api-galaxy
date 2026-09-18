"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { TooltipRoot } from "@/components/ui/primitives";
import { Toaster } from "@/components/toaster";

export function AppProviders({ children }: { children: React.ReactNode }) {
  // One client per browser session. Graph data is expensive to compute and does not
  // change unless the user changes it, so it is cached generously and invalidated
  // explicitly by the mutations that actually alter a project.
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            gcTime: 10 * 60_000,
            refetchOnWindowFocus: false,
            retry: (failureCount, error: any) => {
              if (error?.status && error.status >= 400 && error.status < 500) return false;
              return failureCount < 2;
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <TooltipRoot>
        {children}
        <Toaster />
      </TooltipRoot>
    </QueryClientProvider>
  );
}
