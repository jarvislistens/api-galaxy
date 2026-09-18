"use client";

import { useParams } from "next/navigation";
import { Arena } from "@/components/arena/arena";

export default function Page() {
  const { projectId } = useParams<{ projectId: string }>();
  return <Arena projectId={projectId} />;
}
