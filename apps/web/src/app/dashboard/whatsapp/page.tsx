import { redirect } from "next/navigation";

import { AUTOMATION_PATH } from "@/lib/auth/paths";

export default function DashboardWhatsAppRedirectPage() {
  redirect(AUTOMATION_PATH);
}
