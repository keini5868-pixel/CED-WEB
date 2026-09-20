"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CedButton, HudPanel } from "@ced/ui";

import { fetchShieldStatus, type ShieldStatus } from "@/lib/api/cedShield";
import { CedWordmark } from "@/components/brand/CedWordmark";
import {
  PublicHeaderLink,
  PublicSiteHeader,
} from "@/components/layout/PublicSiteHeader";
import {
  buildRecordSealCall,
  COMPACT_CIRCUIT,
  COMPACT_CONTRACT,
  LACE_NETWORK,
  type CompactRecordSealCall,
} from "@/lib/shield/circuit";
import { DEMO_ARTIFACT, sha256Hex } from "@/lib/shield/hash";
import { connectLace, laceInstalled, type LaceOk } from "@/lib/shield/lace";

type DemoSeal = {
  sealedAt: string;
  wallet: string;
  digest: string;
  call: CompactRecordSealCall;
  writeMode: "client_preview";
};

function Chip({
  ok,
  children,
}: {
  ok: boolean;
  children: string;
}) {
  return (
    <span
      className={[
        "rounded border px-2 py-1 font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest uppercase",
        ok
          ? "border-cyan-500/50 text-cyan-200"
          : "border-amber-500/40 text-amber-100",
      ].join(" ")}
    >
      {children}
    </span>
  );
}

export function ShieldDemoClient() {
  const [hasLace, setHasLace] = useState(false);
  const [wallet, setWallet] = useState<LaceOk | null>(null);
  const [walletError, setWalletError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [digest, setDigest] = useState<string>("");
  const [seal, setSeal] = useState<DemoSeal | null>(null);
  const [copied, setCopied] = useState(false);
  const [apiStatus, setApiStatus] = useState<ShieldStatus | null>(null);

  useEffect(() => {
    setHasLace(laceInstalled());
    const t = window.setInterval(() => setHasLace(laceInstalled()), 1500);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    void fetchShieldStatus().then(setApiStatus);
  }, []);

  const killSwitchOff = apiStatus ? !apiStatus.enabled : true;

  const onConnect = useCallback(async () => {
    setBusy(true);
    setWalletError(null);
    const result = await connectLace(LACE_NETWORK);
    setBusy(false);
    if (!result.ok) {
      if (result.reason === "no_extension") {
        setWalletError(
          "No detecté Lace Midnight. Instale la extensión y recargue esta página.",
        );
      } else if (result.reason === "user_rejected") {
        setWalletError("Conexión cancelada en Lace.");
      } else {
        setWalletError(result.detail || "No pude conectar Lace.");
      }
      setWallet(null);
      return;
    }
    setWallet(result);
  }, []);

  const onSealSample = useCallback(async () => {
    setBusy(true);
    setWalletError(null);
    try {
      const hex = await sha256Hex(DEMO_ARTIFACT);
      setDigest(hex);
      const call = buildRecordSealCall(hex, "session");
      setSeal({
        sealedAt: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
        wallet: wallet?.address || "(conecte Lace para atar la wallet)",
        digest: hex,
        call,
        writeMode: "client_preview",
      });
    } catch (err) {
      setWalletError(err instanceof Error ? err.message : "No pude hashear.");
    } finally {
      setBusy(false);
    }
  }, [wallet?.address]);

  const payloadJson = useMemo(() => {
    if (!seal) return "";
    return JSON.stringify(
      {
        schema: "ced-shield-v1",
        circuit: seal.call.circuit,
        contract: seal.call.contract,
        kind: "session",
        content_sha256: seal.digest,
        sealed_at: seal.sealedAt,
        wallet: seal.wallet,
        write_mode: seal.writeMode,
        never_on_chain: seal.call.neverOnChain,
      },
      null,
      2,
    );
  }, [seal]);

  const onCopy = useCallback(async () => {
    if (!payloadJson) return;
    await navigator.clipboard.writeText(payloadJson);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }, [payloadJson]);

  return (
    <main className="ced-page-glow relative min-h-screen overflow-x-hidden text-[var(--ced-text)]">
      <PublicSiteHeader
        left={
          <PublicHeaderLink href="/">
            <CedWordmark size="sm" />
          </PublicHeaderLink>
        }
        center={
          <span className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-[0.2em] text-cyan-400/80">
            CED SHIELD · MIDNIGHT DEMO
          </span>
        }
        right={
          <div className="flex items-center gap-2">
            <PublicHeaderLink href="/privacy">Privacidad</PublicHeaderLink>
            <PublicHeaderLink href="/">CED</PublicHeaderLink>
          </div>
        }
      />

      <div className="relative z-10 mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6 sm:py-12">
        <div className="flex flex-wrap gap-2">
          <Chip ok={killSwitchOff}>Kill-switch OFF</Chip>
          <Chip ok>Jarvis intacto</Chip>
          <Chip ok={hasLace}>
            {hasLace ? "Lace detectada" : "Lace no detectada"}
          </Chip>
          <Chip ok>Compact 0.16</Chip>
          <Chip ok>Red {LACE_NETWORK}</Chip>
        </div>

        <HudPanel title="QUÉ ES ESTE DEMO">
          <div className="space-y-3 text-sm leading-relaxed text-cyan-100/90">
            <p>
              CED Shield sella que un PDF o una sesión existió. Midnight recibe
              solo el SHA-256, la fecha y la wallet. El contenido se queda en
              CED.
            </p>
            <p className="text-cyan-400/80">
              Esto no es privacidad de la voz. Retell, Gemini, Tavily y Meta no
              pasan por este módulo. El kill-switch{" "}
              <code className="text-cyan-300">CED_SHIELD_ENABLED</code> sigue
              apagado en producción.
            </p>
          </div>
        </HudPanel>

        <div className="grid gap-6 lg:grid-cols-2">
          <HudPanel title="1. CONECTAR LACE">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                Usa <code className="text-cyan-300">window.midnight</code> (DApp
                connector). No se carga midnight.js en el HUD de voz.
              </p>
              <CedButton onClick={() => void onConnect()} disabled={busy}>
                {wallet ? "Reconectar Lace" : "Conectar Lace"}
              </CedButton>
              {wallet ? (
                <dl className="space-y-2 font-mono text-[11px] text-cyan-200/90">
                  <div>
                    <dt className="text-cyan-600">wallet</dt>
                    <dd className="break-all">{wallet.address}</dd>
                  </div>
                  <div>
                    <dt className="text-cyan-600">network</dt>
                    <dd>
                      {wallet.networkId} · {wallet.source}
                    </dd>
                  </div>
                </dl>
              ) : (
                <p className="text-xs text-cyan-500/70">
                  Extensión: Lace Midnight Preview. Red de demo: {LACE_NETWORK}.
                </p>
              )}
              {walletError ? (
                <p className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                  {walletError}
                </p>
              ) : null}
            </div>
          </HudPanel>

          <HudPanel title="2. SELLAR MUESTRA">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                Hashea un artefacto de ejemplo en el navegador y arma la llamada
                a <code className="text-cyan-300">{COMPACT_CIRCUIT}</code> en{" "}
                <code className="text-cyan-300">{COMPACT_CONTRACT}</code>.
              </p>
              <CedButton
                variant="secondary"
                onClick={() => void onSealSample()}
                disabled={busy}
              >
                Hashear y armar circuit
              </CedButton>
              {digest ? (
                <dl className="space-y-2 font-mono text-[11px] text-cyan-200/90">
                  <div>
                    <dt className="text-cyan-600">content_sha256</dt>
                    <dd className="break-all">{digest}</dd>
                  </div>
                  <div>
                    <dt className="text-cyan-600">circuit</dt>
                    <dd>
                      {COMPACT_CIRCUIT}(Bytes&lt;32&gt;, kind=1 SESSION)
                    </dd>
                  </div>
                </dl>
              ) : null}
            </div>
          </HudPanel>
        </div>

        <HudPanel title="PAYLOAD ON-CHAIN (SOLO HASH)" bodyClassName="overflow-auto">
          {seal ? (
            <div className="space-y-3">
              <pre className="max-h-80 overflow-auto rounded border border-cyan-900/60 bg-black/70 p-3 font-mono text-[11px] leading-relaxed text-cyan-100">
                {payloadJson}
              </pre>
              <div className="flex flex-wrap gap-3">
                <CedButton variant="ghost" onClick={() => void onCopy()}>
                  {copied ? "Copiado" : "Copiar payload"}
                </CedButton>
                <p className="self-center text-[11px] text-cyan-600">
                  write_mode = client_preview. La tx ZK en {LACE_NETWORK} es el
                  siguiente paso de Wave 2; este demo no finge un txid.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-cyan-500/70">
              Conecte Lace y selle la muestra para ver el JSON que iría a
              Midnight.
            </p>
          )}
        </HudPanel>

        <HudPanel title="ON-CHAIN VS OFF-CHAIN">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-2 font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-cyan-400">
                VA A MIDNIGHT
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-cyan-100/85">
                <li>content_sha256</li>
                <li>sealed_at</li>
                <li>wallet</li>
                <li>kind (pdf | session)</li>
              </ul>
            </div>
            <div>
              <p className="mb-2 font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-amber-200/80">
                SE QUEDA EN CED
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-cyan-100/85">
                <li>Chat, voz, PDFs</li>
                <li>Audio y transcript</li>
                <li>Meta / Tavily / Gemini</li>
              </ul>
            </div>
          </div>
        </HudPanel>

        <p className="text-center text-[12px] text-cyan-600">
          Módulo piloto. No está en el producto ni en Jarvis.{" "}
          <Link href="/" className="text-cyan-400 hover:text-cyan-200">
            Volver a CED
          </Link>
        </p>
      </div>
    </main>
  );
}
