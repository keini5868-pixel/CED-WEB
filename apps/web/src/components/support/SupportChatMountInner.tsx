"use client";

import dynamic from "next/dynamic";

import { useIsSuperAdminClient } from "@/hooks/useIsSuperAdminClient";

const SupportFloatingButton = dynamic(
  () => import("@/components/support/SupportFloatingButton"),
  { ssr: false },
);

const AdminSupportFloatingButton = dynamic(
  () => import("@/components/support/AdminSupportFloatingButton"),
  { ssr: false },
);

export default function SupportChatMountInner() {
  const { isAdmin, loaded } = useIsSuperAdminClient();

  if (!loaded) return null;
  if (isAdmin) return <AdminSupportFloatingButton />;
  return <SupportFloatingButton />;
}
