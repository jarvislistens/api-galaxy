"use client";

import { useParams } from "next/navigation";
import { BreakLab } from "@/components/break-lab/break-lab";

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  return <BreakLab projectId={projectId} />;
}
