"use client";

import { useParams } from "next/navigation";
import { Settings } from "@/components/settings/settings";

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  return <Settings projectId={projectId} />;
}
