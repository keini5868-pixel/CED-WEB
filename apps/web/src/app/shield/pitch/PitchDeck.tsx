"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

type Slide = {
  kicker: string;
  title: string;
  layout: "hero" | "bullets" | "split" | "steps" | "links";
  body?: string[];
  split?: {
    leftTitle: string;
    left: string[];
    rightTitle: string;
    right: string[];
  };
  steps?: string[];
  links?: { label: string; href: string; external?: boolean }[];
};

const SLIDES: Slide[] = [
  {
    kicker: "AKINDO · Midnight · Wave 2",
    title: "CED Shield",
    layout: "hero",
    body: [
      "A verifiable seal that a PDF or a session existed.",
      "Midnight sees the commitment. The document never leaves CED.",
    ],
  },
  {
    kicker: "Problem",
    title: "Proof without publication",
    layout: "bullets",
    body: [
      "Operators already create PDFs and sessions in CED.",
      "They need to prove the artifact existed — without putting client data, voice, or the file on a public chain.",
    ],
  },
  {
    kicker: "Dual-ledger",
    title: "What is public vs private",
    layout: "split",
    split: {
      leftTitle: "Midnight / Lace",
      left: ["SHA-256", "Timestamp", "Wallet", "Kind · pdf | session"],
      rightTitle: "Stays in CED",
      right: ["PDF bytes", "Audio + transcript", "Prompts", "Social tokens"],
    },
  },
  {
    kicker: "Live path",
    title: "A judge can finish the loop",
    layout: "steps",
    steps: [
      "Lace Midnight Preview · network preprod.",
      "Hash the sample in the browser. SHA-256 never leaves the page.",
      "Sign. If Lace stubs signData, copy the JSON: live wallet + hash, on_chain_txid: null.",
    ],
  },
  {
    kicker: "Engineering",
    title: "Compact is in the repo",
    layout: "bullets",
    body: [
      "CedShield.compact · circuit recordSeal(contentHash, kind) · Compact 0.16.",
      "Apache-2.0 on the Midnight folder. Tests in test_ced_shield.py.",
      "On-chain send waits for deploy + ZK keys. We will not invent a txid.",
    ],
  },
  {
    kicker: "Product",
    title: "Why this is not another DeFi demo",
    layout: "bullets",
    body: [
      "CED already has users, voice, and PDFs. Midnight needs apps with a job to do.",
      "Example: prove a growth report existed without exposing a referral network.",
      "Jarvis, Retell, and Meta never enter this rail. Kill-switch stays off in the product.",
    ],
  },
  {
    kicker: "Wave 2 → Wave 3",
    title: "Honest scope",
    layout: "bullets",
    body: [
      "This wave: live Lace attestation + Compact source + a judge-repeatable demo.",
      "Next: one real preprod transaction when the contract and ZK keys exist.",
      "We do not claim an on-chain send we cannot show.",
    ],
  },
  {
    kicker: "Verify",
    title: "Open these",
    layout: "links",
    links: [
      { label: "Live demo", href: "/shield" },
      {
        label: "CedShield.compact",
        href: "https://github.com/keini5868-pixel/CED-WEB/blob/main/apps/api/app/services/ced_shield/compact/CedShield.compact",
        external: true,
      },
      {
        label: "Repo · CED-WEB",
        href: "https://github.com/keini5868-pixel/CED-WEB",
        external: true,
      },
    ],
    body: [
      "Grant wallet is the 0x USDT (Ethereum) address on the AKINDO profile.",
    ],
  },
];

export function PitchDeck() {
  const [i, setI] = useState(0);
  const last = SLIDES.length - 1;

  const go = useCallback(
    (n: number) => {
      setI(Math.max(0, Math.min(last, n)));
    },
    [last],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault();
        go(i + 1);
      }
      if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        go(i - 1);
      }
      if (e.key === "Home") go(0);
      if (e.key === "End") go(last);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, i, last]);

  const s = SLIDES[i];
  if (!s) return null;

  return (
    <main className="ced-page-glow relative min-h-screen overflow-hidden text-cyan-50">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent"
        aria-hidden
      />
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col justify-between px-6 py-8 sm:px-10">
        <header className="flex items-center justify-between font-[family-name:var(--font-orbitron)] text-[10px] uppercase tracking-[0.28em] text-cyan-500">
          <span>CED · Midnight</span>
          <span>
            {String(i + 1).padStart(2, "0")} / {String(SLIDES.length).padStart(2, "0")}
          </span>
        </header>

        <section className="py-10 sm:py-16" aria-live="polite">
          <p className="font-[family-name:var(--font-orbitron)] text-[11px] tracking-[0.35em] text-cyan-400">
            {s.kicker}
          </p>
          <h1 className="mt-4 max-w-4xl font-[family-name:var(--font-orbitron)] text-4xl leading-tight text-cyan-50 sm:text-6xl">
            {s.title}
          </h1>

          {s.layout === "hero" || s.layout === "bullets" ? (
            <ul className="mt-10 max-w-2xl space-y-4 text-lg leading-relaxed text-cyan-100/85">
              {(s.body || []).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}

          {s.layout === "split" && s.split ? (
            <div className="mt-12 grid gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-cyan-500/35 bg-cyan-950/30 p-6">
                <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.28em] text-cyan-400">
                  {s.split.leftTitle}
                </p>
                <ul className="mt-4 space-y-2 text-lg text-cyan-50">
                  {s.split.left.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-lg border border-amber-500/25 bg-amber-950/20 p-6">
                <p className="font-[family-name:var(--font-orbitron)] text-[10px] tracking-[0.28em] text-amber-200/90">
                  {s.split.rightTitle}
                </p>
                <ul className="mt-4 space-y-2 text-lg text-cyan-50">
                  {s.split.right.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}

          {s.layout === "steps" && s.steps ? (
            <ol className="mt-12 max-w-2xl space-y-5">
              {s.steps.map((line, idx) => (
                <li key={line} className="flex gap-4 text-lg leading-relaxed text-cyan-100/90">
                  <span className="font-[family-name:var(--font-orbitron)] text-cyan-400">
                    {idx + 1}
                  </span>
                  <span>{line}</span>
                </li>
              ))}
            </ol>
          ) : null}

          {s.layout === "links" ? (
            <div className="mt-12 space-y-8">
              <div className="flex flex-col gap-3">
                {(s.links || []).map((link) =>
                  link.external ? (
                    <a
                      key={link.href}
                      href={link.href}
                      target="_blank"
                      rel="noreferrer"
                      className="font-[family-name:var(--font-orbitron)] text-xl text-cyan-200 hover:text-cyan-50"
                    >
                      {link.label} ↗
                    </a>
                  ) : (
                    <Link
                      key={link.href}
                      href={link.href}
                      className="font-[family-name:var(--font-orbitron)] text-xl text-cyan-200 hover:text-cyan-50"
                    >
                      {link.label} →
                    </Link>
                  ),
                )}
              </div>
              {(s.body || []).map((line) => (
                <p key={line} className="max-w-xl text-sm text-cyan-500">
                  {line}
                </p>
              ))}
            </div>
          ) : null}
        </section>

        <footer className="space-y-5">
          <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Slides">
            {SLIDES.map((slide, idx) => (
              <button
                key={slide.title}
                type="button"
                role="tab"
                aria-selected={idx === i}
                aria-label={`Slide ${idx + 1}: ${slide.title}`}
                className={[
                  "h-1.5 rounded-full transition-all",
                  idx === i ? "w-8 bg-cyan-300" : "w-3 bg-cyan-900 hover:bg-cyan-700",
                ].join(" ")}
                onClick={() => go(idx)}
              />
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-cyan-900/60 pt-5 text-sm">
            <div className="flex gap-3">
              <button
                type="button"
                className="rounded border border-cyan-700 px-3 py-1 text-cyan-200 hover:bg-cyan-950 disabled:cursor-not-allowed disabled:opacity-30"
                onClick={() => go(i - 1)}
                disabled={i === 0}
              >
                ←
              </button>
              <button
                type="button"
                className="rounded border border-cyan-700 px-3 py-1 text-cyan-200 hover:bg-cyan-950 disabled:cursor-not-allowed disabled:opacity-30"
                onClick={() => go(i + 1)}
                disabled={i === last}
              >
                →
              </button>
              <span className="self-center text-[11px] uppercase tracking-[0.2em] text-cyan-700">
                arrows · space
              </span>
            </div>
            <div className="flex gap-4 text-cyan-500">
              <Link href="/shield" className="hover:text-cyan-200">
                Live demo
              </Link>
              <a
                href="https://github.com/keini5868-pixel/CED-WEB/blob/main/apps/api/app/services/ced_shield/compact/CedShield.compact"
                className="hover:text-cyan-200"
                target="_blank"
                rel="noreferrer"
              >
                Compact
              </a>
            </div>
          </div>
        </footer>
      </div>
    </main>
  );
}
