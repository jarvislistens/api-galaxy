"use client";

import { useParams } from "next/navigation";
import { Reports } from "@/components/reports/reports";

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  return <Reports projectId={projectId} />;
}
