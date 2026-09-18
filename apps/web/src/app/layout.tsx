import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AppProviders } from "@/components/providers";

export const metadata: Metadata = {
  title: "API Galaxy — drop your API, watch it come alive",
  description:
    "Turn OpenAPI specifications into a living, evidence-backed model you can explore, " +
    "question, safely break, repair and share. Local-first, with Ollama by default.",
  applicationName: "API Galaxy",
  authors: [{ name: "The Sunday Builds" }],
};

export const viewport: Viewport = {
  themeColor: "#0a0c10",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-[var(--radius-sm)] focus:bg-[var(--color-accent)] focus:px-3 focus:py-2 focus:text-[13px] focus:font-semibold focus:text-[#0a0c10]"
        >
          Skip to content
        </a>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
