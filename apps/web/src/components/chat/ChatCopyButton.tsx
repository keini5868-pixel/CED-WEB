"use client";

import { Check, Copy } from "lucide-react";
import { useState, type MouseEvent } from "react";

type ChatCopyButtonProps = {
  text: string;
  className?: string;
};

export function ChatCopyButton({ text, className = "" }: ChatCopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const value = (text || "").trim();
  if (!value) return null;

  const copy = async (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore */
    }
  };

  return (
    <button
      type="button"
      onClick={(e) => void copy(e)}
      aria-label={copied ? "Copiado" : "Copiar mensaje"}
      title={copied ? "Copiado" : "Copiar"}
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-cyan-500/35 bg-black/30 text-cyan-200/90 transition hover:border-cyan-400/60 hover:bg-cyan-500/15 hover:text-cyan-100 ${className}`}
    >
      {copied ? (
        <Check className="h-3 w-3" strokeWidth={2.25} />
      ) : (
        <Copy className="h-3 w-3" strokeWidth={2.25} />
      )}
    </button>
  );
}
