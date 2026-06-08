import { redirect } from "next/navigation";

import { LOGIN_PATH } from "@/lib/auth/paths";
import { getSession } from "@/lib/auth/session";

export default async function DriveLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = await getSession();
  if (!user) redirect(LOGIN_PATH);

  return children;
}
