"use client";



import { useCallback, useEffect, useState } from "react";

import { useRouter, useSearchParams } from "next/navigation";



import { CedButton } from "@ced/ui";



import {

  fetchMetaOAuthUrl,

  fetchMetaStatus,

  type MetaConnectionStatus,

} from "@/lib/api/meta";



export const META_CONNECTED_EVENT = "ced:meta-connected";



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



/** Conectar Instagram / Meta — header del dashboard. */

export function ConnectNetworksButton() {

  const [status, setStatus] = useState<MetaConnectionStatus | null>(null);

  const [busy, setBusy] = useState(false);

  const [error, setError] = useState<string | null>(null);



  const refresh = useCallback(async () => {

    const data = await fetchMetaStatus();

    if (data) setStatus(data);

  }, []);



  useEffect(() => {

    void refresh();

    const onConnected = () => void refresh();

    window.addEventListener(META_CONNECTED_EVENT, onConnected);

    return () => window.removeEventListener(META_CONNECTED_EVENT, onConnected);

  }, [refresh]);



  const connect = async () => {

    setBusy(true);

    setError(null);

    try {

      const { url, error: oauthError } = await fetchMetaOAuthUrl();

      if (!url) {

        setError(
          oauthError ||
            "No se pudo iniciar OAuth. ¿API activa y META configurado?",
        );

        return;

      }

      window.location.href = url;

    } catch {

      setError("Error al conectar con Meta.");

    } finally {

      setBusy(false);

    }

  };



  if (status?.connected) {

    const label = status.username ? `@${status.username}` : "CONECTADO";

    return (

      <button

        type="button"

        onClick={() => void connect()}

        disabled={busy}

        title="Cuenta vinculada. Clic para cambiar de cuenta."

        className="flex items-center gap-2 rounded border border-emerald-400/70 bg-emerald-950/40 px-3 py-2 font-[family-name:var(--font-orbitron)] text-[10px] font-bold tracking-wider text-emerald-200 transition hover:bg-emerald-950/60"

      >

        <span aria-hidden className="text-emerald-400">

          ●

        </span>

        <span>IG · {label}</span>

      </button>

    );

  }



  return (

    <div className="flex flex-col items-end gap-1">

      <CedButton

        variant="secondary"

        type="button"

        disabled={busy}

        onClick={() => void connect()}

        className="!px-3 !py-2 !text-[10px] !tracking-wider"

      >

        {busy ? "CONECTANDO…" : "CONECTAR REDES"}

      </CedButton>

      {error ? (

        <span className="max-w-[200px] text-right text-[10px] text-red-400">

          {error}

        </span>

      ) : null}

    </div>

  );

}

