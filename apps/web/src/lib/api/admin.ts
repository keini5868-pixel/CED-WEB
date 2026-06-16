import { cedApiPath } from "@/lib/api/ced-proxy";

import { parseApiJson } from "@/lib/api/http";



export type ResetMyDailyUsageResult = {

  ok: boolean;

  reset_minutes?: number;

  used_minutes_today?: number;

  plan_minutes_daily?: number;

  blocked?: boolean;

  usage_percent?: number;

  error?: string;

};



export type AdminUserRow = {

  id: string;

  email: string;

  full_name: string | null;

  phone: string | null;

  role: string;

  access_type: string;

  plan: string | null;

  status: string;

  expires_at: string | null;

  minutes_daily: number;

  created_at: string;

  is_founding_member: boolean;

};



export type AdminUsersListResult = {

  users: AdminUserRow[];

  total: number;

  active_count: number;

  expiring_count: number;

};



export type CreateAdminUserPayload = {

  name: string;

  email: string;

  phone?: string;

  access_type: "paid" | "beta" | "founding_gift" | "coadmin";

  plan: "elite_founding" | "elite_regular";

  duration_days: number | "indefinite";

  minutes_daily: number;

  initial_balance: number;

  password: string;

  send_welcome_email: boolean;

  force_password_change: boolean;

  notify_on_first_login: boolean;

  admin_notes?: string;

};



export type CreateAdminUserResult = {

  success: boolean;

  user_id: string;

  email: string;

  login_url: string;

  temporary_password: string;

  expires_at: string | null;

  minutes_daily: number;

  initial_balance: number;

  email_sent: boolean;

  email_error?: string | null;

};



const proxyFetch = (path: string, init?: RequestInit) =>

  fetch(cedApiPath(path), { credentials: "same-origin", ...init });



export async function resetMyDailyUsage(): Promise<ResetMyDailyUsageResult> {

  const res = await proxyFetch("admin/usage/reset-my-daily", {

    method: "POST",

    headers: { "Content-Type": "application/json" },

  });

  const data = await parseApiJson<

    ResetMyDailyUsageResult & { detail?: string }

  >(res);

  if (!res.ok) {
    if (res.status === 403) {
      throw new Error(
        data.detail ||
          "Acceso denegado. Agrega tu email en SUPER_ADMIN_EMAILS en el servicio API (CED-WEB) en Railway.",
      );
    }
    if (res.status === 502) {
      throw new Error(
        data.detail ||
          "No se pudo contactar la API. Revisa NEXT_PUBLIC_API_URL en el servicio web y redeploy.",
      );
    }
    throw new Error(data.detail || data.error || "No se pudo renovar el cupo");
  }

  return data;

}



export async function fetchAdminUsers(

  search = "",

): Promise<AdminUsersListResult> {

  const q = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";

  const res = await proxyFetch(`admin/users${q}`);

  const data = await parseApiJson<AdminUsersListResult & { detail?: string }>(

    res,

  );

  if (!res.ok) {

    throw new Error(data.detail || "No se pudo cargar usuarios");

  }

  return data;

}



export async function createAdminUser(

  payload: CreateAdminUserPayload,

): Promise<CreateAdminUserResult> {

  const res = await proxyFetch("admin/users/create", {

    method: "POST",

    headers: { "Content-Type": "application/json" },

    body: JSON.stringify(payload),

  });

  const data = await parseApiJson<CreateAdminUserResult & { detail?: string }>(

    res,

  );

  if (!res.ok) {

    throw new Error(

      typeof data.detail === "string"

        ? data.detail

        : "No se pudo crear el usuario",

    );

  }

  return data;

}


