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

/** Activa por defecto; solo se oculta con NEXT_PUBLIC_SUPPORT_CHAT_ENABLED=false */
export function SupportChatMount() {
  const { isAdmin, loaded } = useIsSuperAdminClient();

  if (process.env.NEXT_PUBLIC_SUPPORT_CHAT_ENABLED === "false") return null;
  if (!loaded) return null;

  if (isAdmin) return <AdminSupportFloatingButton />;
  return <SupportFloatingButton />;
}
