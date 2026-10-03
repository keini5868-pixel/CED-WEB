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

const GITHUB_REPO = "https://github.com/keini5868-pixel/CED-WEB";
const GITHUB_COMPACT =
  "https://github.com/keini5868-pixel/CED-WEB/blob/main/apps/api/app/services/ced_shield/compact/CedShield.compact";

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
          "Lace Midnight not detected. Install the extension and reload this page.",
        );
      } else if (result.reason === "user_rejected") {
        setWalletError("Connection cancelled in Lace.");
      } else {
        setWalletError(
          result.detail ||
            "Could not connect Lace. Open the extension icon, reload, and try again.",
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
        wallet: wallet?.address || "(connect Lace to bind the wallet)",
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
      setWalletError(err instanceof Error ? err.message : "Could not hash.");
    } finally {
      setBusy(false);
    }
  }, [wallet?.address]);

  const onSign = useCallback(async () => {
    if (!digest) {
      setWalletError("Hash the sample first.");
      return;
    }
    if (!wallet) {
      setWalletError("Connect Lace before signing.");
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
        setWalletError("Signature cancelled in Lace.");
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
          "Seal ready. Lace does not implement signData; no fake signature or txid. Copy the JSON: live wallet + SHA-256.",
        );
        return;
      }
      if (!result.ok) {
        setWalletError(result.detail || "Lace did not sign the seal.");
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
          "No invented txid or signature. recordSeal on-chain needs a deployed contract + ZK keys. Lace ConnectedAPI does not implement signData; the seal is live-wallet + SHA-256 on preprod.",
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
            <PublicHeaderLink href="/shield/pitch">Deck</PublicHeaderLink>
            <PublicHeaderLink href="/privacy">Privacy</PublicHeaderLink>
            <PublicHeaderLink href="/">CED</PublicHeaderLink>
          </div>
        }
      />

      <div className="relative z-10 mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6 sm:py-12">
        <div className="flex flex-wrap gap-2">
          <Chip ok={killSwitchOff}>Kill-switch OFF</Chip>
          <Chip ok>Jarvis untouched</Chip>
          <Chip ok={hasLace}>
            {hasLace ? "Lace detected" : "Lace not detected"}
          </Chip>
          <Chip ok={Boolean(wallet)}>
            {wallet ? "Live wallet" : "Wallet not connected"}
          </Chip>
          <Chip ok={signed || seal?.writeMode === "lace_bound"}>
            {signed
              ? "Seal signed"
              : seal?.writeMode === "lace_bound"
                ? "Seal ready"
                : "No signature"}
          </Chip>
          <Chip ok>Compact 0.16</Chip>
          <Chip ok>Network {LACE_NETWORK}</Chip>
        </div>

        <HudPanel title="WHAT THIS DEMO IS">
          <div className="space-y-3 text-sm leading-relaxed text-cyan-100/90">
            <p>
              CED Shield proves a PDF or a session existed. Midnight and Lace
              see only the SHA-256, the timestamp, and the wallet. The content
              stays in CED.
            </p>
            <p className="text-cyan-400/80">
              Solid Wave 2 path: Lace attests the commitment (
              <code className="text-cyan-300">signData</code>
              ). No fake txid. Circuit{" "}
              <code className="text-cyan-300">{COMPACT_CIRCUIT}</code> in{" "}
              <code className="text-cyan-300">{COMPACT_CONTRACT}</code> is the
              contract; an on-chain send waits for deploy + ZK keys. Jarvis,
              Retell, and Meta never enter this path.{" "}
              <code className="text-cyan-300">CED_SHIELD_ENABLED</code> stays
              off in the product.
            </p>
          </div>
        </HudPanel>

        <HudPanel title="HOW A JUDGE VERIFIES">
          <ol className="list-decimal space-y-2 pl-5 text-sm text-cyan-100/90">
            <li>Connect Lace Midnight Preview on {LACE_NETWORK}.</li>
            <li>Hash the sample in the browser (SHA-256 never leaves this page).</li>
            <li>
              Sign. If Lace stubs <code className="text-cyan-300">signData</code>
              , copy the JSON: live wallet + hash,{" "}
              <code className="text-cyan-300">on_chain_txid: null</code>.
            </li>
          </ol>
          <p className="mt-3 text-xs text-cyan-500/80">
            GitHub:{" "}
            <a
              href={GITHUB_COMPACT}
              className="text-cyan-400 hover:text-cyan-200"
              target="_blank"
              rel="noreferrer"
            >
              {COMPACT_CONTRACT} · {COMPACT_CIRCUIT}
            </a>
            {" · "}
            <a
              href={GITHUB_REPO}
              className="text-cyan-400 hover:text-cyan-200"
              target="_blank"
              rel="noreferrer"
            >
              CED-WEB repo
            </a>
          </p>
        </HudPanel>

        <div className="grid gap-6 lg:grid-cols-3">
          <HudPanel title="1. CONNECT LACE">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                <code className="text-cyan-300">window.midnight</code> — DApp
                connector. It does not enter the voice HUD.
              </p>
              <CedButton onClick={() => void onConnect()} disabled={busy}>
                {wallet ? "Reconnect Lace" : "Connect Lace"}
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
                    <dd>{live?.canSignData ? "yes" : "no"}</dd>
                  </div>
                </dl>
              ) : (
                <p className="text-xs text-cyan-500/70">
                  Extension: Lace Midnight Preview. Network: {LACE_NETWORK}.
                </p>
              )}
            </div>
          </HudPanel>

          <HudPanel title="2. HASH SAMPLE">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                SHA-256 in the browser. Compact expects{" "}
                <code className="text-cyan-300">Bytes&lt;32&gt;</code> + kind.
              </p>
              <CedButton
                variant="secondary"
                onClick={() => void onHash()}
                disabled={busy}
              >
                Hash sample
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

          <HudPanel title="3. SIGN IN LACE">
            <div className="space-y-4">
              <p className="text-xs leading-relaxed text-cyan-500/80">
                We request signData from Lace. Today the extension returns that
                the method is not implemented. The seal is still wallet + hash,
                with no invented signature.
              </p>
              <CedButton
                onClick={() => void onSign()}
                disabled={busy || !digest || !wallet}
              >
                Sign seal in Lace
              </CedButton>
              {signed ? (
                <p className="text-xs text-cyan-300">
                  Signature received. Verifying key is in the JSON below.
                </p>
              ) : seal?.writeMode === "lace_bound" ? (
                <p className="text-xs text-cyan-300">
                  Lace did not sign. Copy the JSON: that is the Wave 2 artifact.
                </p>
              ) : (
                <p className="text-xs text-cyan-500/70">
                  After connect and hash, press here. If Lace does not sign, the
                  JSON below still counts.
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

        <HudPanel title="SEAL (HASH + SIGNATURE, NO CONTENT)" bodyClassName="overflow-auto">
          {seal ? (
            <div className="space-y-3">
              <pre className="max-h-80 overflow-auto rounded border border-cyan-900/60 bg-black/70 p-3 font-mono text-[11px] leading-relaxed text-cyan-100">
                {payloadJson}
              </pre>
              <div className="flex flex-wrap gap-3">
                <CedButton variant="ghost" onClick={() => void onCopy()}>
                  {copied ? "Copied" : "Copy seal"}
                </CedButton>
                <p className="self-center text-[11px] text-cyan-600">
                  write_mode = {seal.writeMode}. on_chain_txid = null on
                  purpose.
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-cyan-500/70">
              Connect Lace, hash, and sign to see the seal a judge can verify.
            </p>
          )}
        </HudPanel>

        <HudPanel title="ON-CHAIN VS OFF-CHAIN">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="mb-2 font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-cyan-400">
                GOES TO MIDNIGHT / LACE
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-cyan-100/85">
                <li>content_sha256</li>
                <li>sealed_at</li>
                <li>wallet + unshielded signature</li>
                <li>kind (pdf | session)</li>
              </ul>
            </div>
            <div>
              <p className="mb-2 font-[family-name:var(--font-orbitron)] text-[10px] tracking-widest text-amber-200/80">
                STAYS IN CED
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-cyan-100/85">
                <li>Chat, voice, PDFs</li>
                <li>Audio and transcript</li>
                <li>Meta / Tavily / Gemini</li>
              </ul>
            </div>
          </div>
        </HudPanel>

        <p className="text-center text-[12px] text-cyan-600">
          Pilot module. Not in Jarvis. English for AKINDO judges.{" "}
          <Link href="/shield/pitch" className="text-cyan-400 hover:text-cyan-200">
            Wave 2 deck
          </Link>
          {" · "}
          <Link href="/" className="text-cyan-400 hover:text-cyan-200">
            Back to CED
          </Link>
        </p>
      </div>
    </main>
  );
}
