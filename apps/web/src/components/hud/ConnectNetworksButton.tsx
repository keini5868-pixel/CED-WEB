"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { CedButton } from "@ced/ui";

import { useConnectNetworks, META_CONNECTED_EVENT } from "@/components/hud/useConnectNetworks";

export { META_CONNECTED_EVENT };

const META_TOAST: Record<string, string> = {
  connected: "Instagram conectado correctamente.",
  error: "No se pudo conectar Instagram. Inténtelo de nuevo.",
  token_failed: "Meta no devolvió token. Revise permisos de la app.",
  no_ig: "La página de Facebook no tiene Instagram Business vinculado.",
  missing_config: "META_APP_ID no configurado en el servidor.",
};

/** Muestra toast tras redirect OAuth (?meta=connected). */
export function MetaOAuthCallbackBanner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const meta = searchParams.get("meta");
    if (!meta) return;
    setMessage(META_TOAST[meta] ?? `Resultado Meta: ${meta}`);
    if (meta === "connected") {
      window.dispatchEvent(new Event(META_CONNECTED_EVENT));
    }
    router.replace("/dashboard", { scroll: false });
  }, [searchParams, router]);

  if (!message) return null;

  const ok = message.includes("correctamente");
  return (
    <div
      className={[
        "mx-auto mb-3 max-w-2xl rounded border px-4 py-2 text-center text-sm",
        ok
          ? "border-emerald-500/50 bg-emerald-950/40 text-emerald-200"
          : "border-red-500/50 bg-red-950/40 text-red-200",
      ].join(" ")}
      role="status"
    >
      {message}
    </div>
  );
}

/** Conectar Instagram / Meta — header del dashboard (desktop). */
export function ConnectNetworksButton() {
  const { status, busy, error, connect } = useConnectNetworks();

  if (status?.connected) {
    const label = status.username ? `@${status.username}` : "CONECTADO";
    return (
      <button
        type="button"
        onClick={() => void connect()}
        disabled={busy}
        title="Cuenta vinculada. Clic para cambiar de cuenta."
        className="flex max-w-[9.5rem] items-center gap-1.5 truncate rounded border border-emerald-400/70 bg-emerald-950/40 px-2 py-1.5 font-[family-name:var(--font-orbitron)] text-[9px] font-bold tracking-wider text-emerald-200 transition hover:bg-emerald-950/60 sm:max-w-none sm:gap-2 sm:px-3 sm:text-[10px]"
      >
        <span aria-hidden className="text-emerald-400">
          ●
        </span>
        <span>IG · {label}</span>
      </button>
    );
  }

  return (
    <div className="flex flex-col items-center gap-1 md:items-end">
      <CedButton
        variant="secondary"
        type="button"
        disabled={busy}
        onClick={() => void connect()}
        className="!px-2.5 !py-1.5 !text-[9px] !tracking-wider sm:!px-3 sm:!text-[10px]"
      >
        {busy ? "CONECTANDO…" : (
          <>
            <span className="sm:hidden">REDES</span>
            <span className="hidden sm:inline">CONECTAR REDES</span>
          </>
        )}
      </CedButton>
      {error ? (
        <span className="max-w-[200px] text-right text-[10px] text-red-400">{error}</span>
      ) : null}
    </div>
  );
}
