"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useDriveMap } from "@/contexts/DriveMapContext";
import { DASHBOARD_PATH } from "@/lib/auth/paths";

/** /drive abre el overlay en el dashboard sin desmontar la sesión de voz. */
export default function DriveRedirectPage() {
  const router = useRouter();
  const { openDriveMap } = useDriveMap();

  useEffect(() => {
    openDriveMap();
    router.replace(DASHBOARD_PATH);
  }, [openDriveMap, router]);

  return null;
}
