import type { Metadata } from "next";
import { Landing } from "@/components/landing/landing";

export const metadata: Metadata = {
  title: "API Galaxy — drop your API, watch it come alive",
};

export default function HomePage() {
  return <Landing />;
}
