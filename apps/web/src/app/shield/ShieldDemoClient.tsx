"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { CedButton, HudPanel } from "@ced/ui";

import { fetchShieldStatus, type ShieldStatus } from "@/lib/api/cedShield";
import { CedWordmark } from "@/components/brand/CedWordmark";
import {
  PublicHeaderLink,
  PublicSiteHeader,
} from "@/components/layout/PublicSiteHeader";
import {
  COMPACT_CIRCUIT,
  COMPACT_CONTRACT,
  LACE_NETWORK,
} from "@/lib/shield/circuit";
import {
  buildShieldCommitment,
  commitmentMessage,
  utf8ToHex,
  utcNowIso,
  type ShieldCommitment,
} from "@/lib/shield/commitment";
import { DEMO_ARTIFACT, sha256Hex } from "@/lib/shield/hash";
import {
  connectLace,
  laceInstalled,
  readLaceLive,
  signCommitmentHex,
  type LaceLiveSnapshot,
  type LaceOk,
  type LaceSignature,
} from "@/lib/shield/lace";

type DemoSeal = {
  commitment: ShieldCommitment;
  message: string;
  messageHex: string;
  signature: LaceSignature | null;
  writeMode: "lace_attestation" | "lace_bound" | "client_preview";
};

function Chip({
  ok,
  children,
}: {
  ok: boolean;
  children: ReactNode;
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
  const [live, setLive] = useState<LaceLiveSnapshot | null>(null);
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
  const signed = Boolean(seal?.signature);

  const refreshLive = useCallback(async () => {
    const snap = await readLaceLive();
    setLive(snap);
    return snap;
  }, []);

  const onConnect = useCallback(async () => {
    setBusy(true);
    setWalletError(null);
    const result = await connectLace(LACE_NETWORK);
    if (!result.ok) {
      if (result.reason === "no_extension") {
        setWalletError(
          "No detecté Lace Midnight. Instale la extensión y recargue esta página.",
        );
      } else if (result.reason === "user_rejected") {
        setWalletError("Conexión cancelada en Lace.");
      } else {
        setWalletError(
          result.detail ||
            "No pude conectar Lace. Abra el icono de la extensión, recargue y pruebe otra vez.",
        );
      }
      setWallet(null);
      setLive(null);
      setBusy(false);
      return;
    }
    setWallet(result);
    const snap = await refreshLive();
    const liveAddress = snap?.address || result.address;
    if (liveAddress !== result.address) {
      setWallet({ ...result, address: liveAddress });
    }
    setSeal((prev) => {
      if (!prev) return prev;
      const commitment = buildShieldCommitment({
        contentSha256: prev.commitment.content_sha256,
        kind: prev.commitment.kind,
        sealedAt: prev.commitment.sealed_at,
        wallet: liveAddress,
      });
      const message = commitmentMessage(commitment);
      return {
        ...prev,
        commitment,
        message,
        messageHex: utf8ToHex(message),
        signature: null,
        writeMode: "client_preview",
      };
    });
    setBusy(false);
  }, [refreshLive]);

  const onHash = useCallback(async () => {
    setBusy(true);
    setWalletError(null);
    try {
      const hex = await sha256Hex(DEMO_ARTIFACT);
      setDigest(hex);
      const commitment = buildShieldCommitment({
        contentSha256: hex,
        kind: "session",
        sealedAt: utcNowIso(),
        wallet: wallet?.address || "(conecte Lace para atar la wallet)",
      });
      const message = commitmentMessage(commitment);
      setSeal({
        commitment,
        message,
        messageHex: utf8ToHex(message),
        signature: null,
        writeMode: "client_preview",
      });
    } catch (err) {
      setWalletError(err instanceof Error ? err.message : "No pude hashear.");
    } finally {
      setBusy(false);
    }
  }, [wallet?.address]);

  const onSign = useCallback(async () => {
    if (!digest) {
      setWalletError("Primero hashee la muestra.");
      return;
    }
    if (!wallet) {
      setWalletError("Conecte Lace antes de firmar.");
      return;
    }
    setBusy(true);
    setWalletError(null);
    try {
      const snap = await refreshLive();
      const liveAddress = snap?.address || wallet.address;
      setWallet((prev) =>
        prev && liveAddress !== prev.address
          ? { ...prev, address: liveAddress }
          : prev,
      );
      const commitment = buildShieldCommitment({
        contentSha256: digest,
        kind: "session",
        sealedAt: seal?.commitment.sealed_at || utcNowIso(),
        wallet: liveAddress,
      });
      const message = commitmentMessage(commitment);
      const messageHex = utf8ToHex(message);
      const result = await signCommitmentHex(messageHex, message);
      if (!result.ok && result.reason === "user_rejected") {
        setWalletError("Firma cancelada en Lace.");
        return;
      }
      if (!result.ok && result.reason === "no_signData") {
        setSeal({
          commitment,
          message,
          messageHex,
          signature: null,
          writeMode: "lace_bound",
        });
        setWalletError(
          "Lace no implementa signData todavía. El sello de abajo — wallet + SHA-256 — es el envío. Quédate en /shield y copia el JSON. No vayas a /add-plugin y no se finge firma.",
        );
        return;
      }
      if (!result.ok) {
        setWalletError(result.detail || "Lace no firmó el sello.");
        return;
      }
      setSeal({
        commitment,
        message,
        messageHex,
        signature: result.signature,
        writeMode: "lace_attestation",
      });
    } finally {
      setBusy(false);
    }
  }, [digest, seal?.commitment.sealed_at, wallet]);

  const payloadJson = useMemo(() => {
    if (!seal) return "";
    return JSON.stringify(
      {
        ...seal.commitment,
        write_mode: seal.writeMode,
        lace_network: LACE_NETWORK,
        compact_call: `${COMPACT_CIRCUIT}(Bytes<32>, kind)`,
        attestation: seal.signature
          ? {
              encoding: "hex",
              keyType: "unshielded",
              message: seal.message,
              signature: seal.signature.signature,
              verifyingKey: seal.signature.verifyingKey,
            }
          : null,
        sign_data_status:
          seal.writeMode === "lace_attestation"
            ? "signed"
            : seal.writeMode === "lace_bound"
              ? "lace_not_implemented"
              : "not_attempted",
        on_chain_txid: null,
        on_chain_note:
          "No se inventa txid ni firma. recordSeal on-chain requiere contrato deployado + keys ZK. Lace ConnectedAPI no implementa signData; el sello es hash + wallet viva en preprod.",
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
          <Chip ok={Boolean(wallet)}>
            {wallet ? "Wallet viva" : "Wallet no conectada"}
          </Chip>
          <Chip ok={signed}>{signed ? "Sello firmado" : "Sin firma"}</Chip>
          <Chip ok>Compact 0.16</Chip>
          <Chip ok>Red {LACE_NETWORK}</Chip>
        </div>

        <HudPanel title="QUÉ ES ESTE DEMO">
          <div className="space-y-3 text-sm leading-relaxed text-cyan-100/90">
            <p>
              CED Shield prueba que un PDF o una sesión existió. Midnight y Lace
              ven solo el SHA-256, la fecha y la wallet. El contenido se queda
              en CED.
            </p>
            <p className="text-cyan-400/80">
              Paso sólido de Wave 2: Lace firma el compromiso (
              <code className="text-cyan-300">signData</code>
              ). No se finge un txid. La circuit{" "}
              <code className="text-cyan-300">{COMPACT_CIRCUIT}</code> en{" "}
              <code className="text-cyan-300">{COMPACT_CONTRACT}</code> es el
              contrato; el envío on-chain entra cuando haya deploy + keys ZK.
              Jarvis, Retell y Meta no pasan por aquí.{" "}
              <code className="text-cyan-300">CED_SHIELD_ENABLED</code> sigue
              apagado en el producto.
            </p>
          </div>
        </HudPanel>

        <div className="grid gap-6 lg:grid-cols-3">
          <HudPanel title="1. CONECTAR LACE">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                <code className="text-cyan-300">window.midnight</code> — DApp
                connector. No entra al HUD de voz.
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
                      {live?.networkId || wallet.networkId} · {wallet.source}
                    </dd>
                  </div>
                  {live?.indexerUri ? (
                    <div>
                      <dt className="text-cyan-600">indexer</dt>
                      <dd className="break-all">{live.indexerUri}</dd>
                    </div>
                  ) : null}
                  {live?.dustBalance ? (
                    <div>
                      <dt className="text-cyan-600">dust</dt>
                      <dd>{live.dustBalance}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt className="text-cyan-600">signData</dt>
                    <dd>{live?.canSignData ? "sí" : "no"}</dd>
                  </div>
                </dl>
              ) : (
                <p className="text-xs text-cyan-500/70">
                  Extensión: Lace Midnight Preview. Red: {LACE_NETWORK}.
                </p>
              )}
            </div>
          </HudPanel>

          <HudPanel title="2. HASH MUESTRA">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                SHA-256 en el navegador. Compact espera{" "}
                <code className="text-cyan-300">Bytes&lt;32&gt;</code> + kind.
              </p>
              <CedButton
                variant="secondary"
                onClick={() => void onHash()}
                disabled={busy}
              >
                Hashear muestra
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
                      {COMPACT_CIRCUIT}(hash, SESSION)
                    </dd>
                  </div>
                </dl>
              ) : null}
            </div>
          </HudPanel>

          <HudPanel title="3. FIRMAR EN LACE">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                La extensión firma el compromiso. Eso es una atestación de
                wallet Midnight, no un tx Compact inventado.
              </p>
              <CedButton
                onClick={() => void onSign()}
                disabled={busy || !digest || !wallet}
              >
                Firmar sello en Lace
              </CedButton>
              {signed ? (
                <p className="text-xs text-cyan-300">
                  Firma recibida. Verifying key en el JSON de abajo.
                </p>
              ) : (
                <p className="text-xs text-cyan-500/70">
                  Si Lace dice «método no implementado», recargue y firme otra
                  vez. Preview 2.39 a veces stubbea signData; la wallet y el
                  hash igual cuentan.
                </p>
              )}
            </div>
          </HudPanel>
        </div>

        {walletError ? (
          <p className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            {walletError}
          </p>
        ) : null}

        <HudPanel title="SELLO (HASH + FIRMA, SIN CONTENIDO)" bodyClassName="overflow-auto">
          {seal ? (
            <div className="space-y-3">
              <pre className="max-h-80 overflow-auto rounded border border-cyan-900/60 bg-black/70 p-3 font-mono text-[11px] leading-relaxed text-cyan-100">
                {payloadJson}
              </pre>
              <div className="flex flex-wrap gap-3">
                <CedButton variant="ghost" onClick={() => void onCopy()}>
                  {copied ? "Copiado" : "Copiar sello"}
                </CedButton>
                <p className="self-center text-[11px] text-cyan-600">
                  write_mode = {seal.writeMode}. on_chain_txid = null a
                  propósito.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-cyan-500/70">
              Conecte Lace, hashee y firme para ver el sello que un juez puede
              verificar.
            </p>
          )}
        </HudPanel>

        <HudPanel title="ON-CHAIN VS OFF-CHAIN">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-2 font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-cyan-400">
                VA A MIDNIGHT / LACE
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-cyan-100/85">
                <li>content_sha256</li>
                <li>sealed_at</li>
                <li>wallet + firma unshielded</li>
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
          Módulo piloto. No está en Jarvis.{" "}
          <Link href="/" className="text-cyan-400 hover:text-cyan-200">
            Volver a CED
          </Link>
        </p>
      </div>
    </main>
  );
}
