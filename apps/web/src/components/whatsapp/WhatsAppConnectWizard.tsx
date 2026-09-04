"use client";

import { useState } from "react";
import { CheckCircle2, ChevronLeft, ChevronRight, Circle } from "lucide-react";

const STEPS = [
  { id: 1, title: "Tu número" },
  { id: 2, title: "Cuenta de mensajería" },
  { id: 3, title: "Pegar datos" },
  { id: 4, title: "Tu objetivo" },
] as const;

type WhatsAppConnectWizardProps = {
  hubUrl: string;
  addonPrice: number;
  busy: boolean;
  error: string | null;
  connectionKey: string;
  phoneId: string;
  displayPhone: string;
  goal: string;
  ctaUrl: string;
  ctaLabel: string;
  onConnectionKeyChange: (value: string) => void;
  onPhoneIdChange: (value: string) => void;
  onDisplayPhoneChange: (value: string) => void;
  onGoalChange: (value: string) => void;
  onCtaUrlChange: (value: string) => void;
  onCtaLabelChange: (value: string) => void;
  onConnect: () => void | Promise<void>;
};

function StepBadge({ n, active, done }: { n: number; active: boolean; done: boolean }) {
  if (done) {
    return (
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-300">
        <CheckCircle2 className="h-4 w-4" />
      </span>
    );
  }
  return (
    <span
      className={[
        "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold",
        active
          ? "bg-cyan-500/30 text-cyan-100 ring-2 ring-cyan-400/50"
          : "bg-cyan-950/60 text-cyan-500/70",
      ].join(" ")}
    >
      {n}
    </span>
  );
}

function PanelMockGuide() {
  return (
    <div
      className="mt-3 overflow-hidden rounded-lg border border-cyan-700/40 bg-[#0a1218] text-[10px] leading-snug text-cyan-100/80 sm:text-[11px]"
      aria-hidden
    >
      <div className="border-b border-cyan-800/50 bg-cyan-950/40 px-3 py-2 font-semibold text-cyan-200">
        Panel de tu canal (ejemplo)
      </div>
      <div className="space-y-2 p-3">
        <div className="rounded border border-amber-500/40 bg-amber-950/20 px-2 py-1.5">
          <span className="font-semibold text-amber-200">① Clave de conexión</span>
          <p className="mt-0.5 font-mono text-[9px] text-cyan-100/70">
            xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
          </p>
          <p className="text-cyan-100/50">Menú del canal → API Keys → Copiar</p>
        </div>
        <div className="rounded border border-sky-500/40 bg-sky-950/20 px-2 py-1.5">
          <span className="font-semibold text-sky-200">② ID de tu número</span>
          <p className="mt-0.5 font-mono text-[9px] text-cyan-100/70">123456789012345</p>
          <p className="text-cyan-100/50">WhatsApp → Phone number ID (números largos)</p>
        </div>
      </div>
      <p className="border-t border-cyan-800/40 px-3 py-2 text-[10px] text-cyan-100/45">
        Si no ves estos campos, abre tu canal en el panel y busca la sección WhatsApp /
        API.
      </p>
    </div>
  );
}

export function WhatsAppConnectWizard({
  hubUrl,
  addonPrice,
  busy,
  error,
  connectionKey,
  phoneId,
  displayPhone,
  goal,
  ctaUrl,
  ctaLabel,
  onConnectionKeyChange,
  onPhoneIdChange,
  onDisplayPhoneChange,
  onGoalChange,
  onCtaUrlChange,
  onCtaLabelChange,
  onConnect,
}: WhatsAppConnectWizardProps) {
  const [step, setStep] = useState(1);

  const canAdvanceFrom3 = connectionKey.trim().length > 8 && phoneId.trim().length > 5;

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-cyan-500/30 bg-gradient-to-b from-cyan-950/30 to-black/40 p-4 sm:p-5">
        <p className="text-sm text-cyan-100/85">
          En unos minutos CED podrá responder por ti en WhatsApp con la misma inteligencia
          del chat. Sigue los 4 pasos — no necesitas ser técnico.
        </p>
        <p className="mt-2 text-xs text-cyan-100/50">
          Módulo CED WhatsApp: ${addonPrice.toFixed(0)} USD/mes (además del costo del
          proveedor de mensajes y lo que cobre Meta por conversación).
        </p>
      </div>

      <ol className="flex gap-1 sm:gap-2">
        {STEPS.map((s) => (
          <li key={s.id} className="flex flex-1 flex-col items-center gap-1">
            <StepBadge n={s.id} active={step === s.id} done={step > s.id} />
            <span
              className={[
                "hidden text-center text-[9px] leading-tight sm:block",
                step === s.id ? "text-cyan-100" : "text-cyan-100/45",
              ].join(" ")}
            >
              {s.title}
            </span>
          </li>
        ))}
      </ol>

      {step === 1 ? (
        <section className="space-y-3 rounded-lg border border-cyan-800/50 bg-black/35 p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-cyan-50">
            <StepBadge n={1} active done={false} />
            Paso 1 — Un número solo para el negocio
          </h2>
          <p className="text-sm text-cyan-100/75">
            Necesitas un <strong>número de teléfono dedicado</strong> para WhatsApp
            Business. <strong>No uses tu WhatsApp personal</strong>: Meta no permite
            mezclarlos y pierdes el historial personal.
          </p>
          <ul className="list-disc space-y-1 pl-5 text-xs text-cyan-100/65">
            <li>Puede ser una línea nueva de tu operador.</li>
            <li>
              En EE.UU. puedes conseguir uno gratis con{" "}
              <a
                href="https://voice.google.com/"
                target="_blank"
                rel="noreferrer"
                className="text-cyan-300 underline"
              >
                Google Voice
              </a>{" "}
              (elige un número y verifícalo con tu cuenta Google).
            </li>
            <li>Ese mismo número lo registrarás en el paso 2.</li>
          </ul>
        </section>
      ) : null}

      {step === 2 ? (
        <section className="space-y-3 rounded-lg border border-cyan-800/50 bg-black/35 p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-cyan-50">
            <StepBadge n={2} active done={false} />
            Paso 2 — Crea tu cuenta de mensajería
          </h2>
          <p className="text-sm text-cyan-100/75">
            Usamos un proveedor oficial de WhatsApp para que tus mensajes lleguen de forma
            estable y el número siga siendo <strong>tuyo</strong>. Solo creas la cuenta
            una vez.
          </p>
          <a
            href={hubUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center rounded-lg border border-cyan-400/50 bg-cyan-950/50 px-4 py-2.5 text-sm font-semibold text-cyan-100 hover:bg-cyan-900/40"
          >
            Abrir panel de registro →
          </a>
          <ol className="list-decimal space-y-1.5 pl-5 text-xs text-cyan-100/65">
            <li>Inicia sesión o crea cuenta.</li>
            <li>Conecta tu Meta Business (Facebook del negocio).</li>
            <li>Registra el número del paso 1 y verifica el código SMS.</li>
            <li>Cuando veas tu canal activo, vuelve aquí al paso 3.</li>
          </ol>
        </section>
      ) : null}

      {step === 3 ? (
        <section className="space-y-3 rounded-lg border border-cyan-800/50 bg-black/35 p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-cyan-50">
            <StepBadge n={3} active done={false} />
            Paso 3 — Copia estos 2 datos y pégalos aquí
          </h2>
          <p className="text-sm text-cyan-100/75">
            En el panel del paso 2 encontrarás dos códigos. Cópialos tal cual (sin
            espacios extra):
          </p>
          <PanelMockGuide />
          <label className="block text-xs text-cyan-100/80">
            ① Clave de conexión
            <input
              type="password"
              value={connectionKey}
              onChange={(e) => onConnectionKeyChange(e.target.value)}
              placeholder="Pega aquí la clave larga del panel"
              className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              autoComplete="off"
            />
          </label>
          <label className="block text-xs text-cyan-100/80">
            ② ID de tu número
            <input
              value={phoneId}
              onChange={(e) => onPhoneIdChange(e.target.value)}
              placeholder="Serie de números (15 dígitos aprox.)"
              className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              inputMode="numeric"
            />
          </label>
          <label className="block text-xs text-cyan-100/60">
            Tu número visible (opcional, ej. +1 849 555 1234)
            <input
              value={displayPhone}
              onChange={(e) => onDisplayPhoneChange(e.target.value)}
              className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-3 py-2 text-sm text-cyan-50"
            />
          </label>
        </section>
      ) : null}

      {step === 4 ? (
        <section className="space-y-3 rounded-lg border border-cyan-800/50 bg-black/35 p-4">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-cyan-50">
            <StepBadge n={4} active done={false} />
            Paso 4 — ¿A dónde quieres que CED guíe a quien te escriba?
          </h2>
          <p className="text-sm text-cyan-100/75">
            CED responderá con inteligencia y buscará llevar a cada persona hacia este
            objetivo. Puedes cambiarlo después.
          </p>
          <label className="block text-xs text-cyan-100/80">
            Tu objetivo
            <textarea
              value={goal}
              onChange={(e) => onGoalChange(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              placeholder='Ej. "Que se unan a mi grupo de WhatsApp" o "Que pidan el enlace de inscripción FitLine".'
            />
          </label>
          <label className="block text-xs text-cyan-100/60">
            Enlace o grupo (opcional)
            <input
              value={ctaUrl}
              onChange={(e) => onCtaUrlChange(e.target.value)}
              className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              placeholder="https://chat.whatsapp.com/..."
            />
          </label>
          <label className="block text-xs text-cyan-100/60">
            Nombre de ese enlace (opcional)
            <input
              value={ctaLabel}
              onChange={(e) => onCtaLabelChange(e.target.value)}
              className="mt-1 w-full rounded border border-cyan-800/60 bg-black/50 px-3 py-2 text-sm text-cyan-50"
              placeholder="Grupo de onboarding"
            />
          </label>
          <button
            type="button"
            disabled={busy || !canAdvanceFrom3}
            onClick={() => void onConnect()}
            className="mt-2 w-full rounded-lg border border-emerald-400/60 bg-emerald-950/50 px-4 py-3 text-sm font-bold tracking-wide text-emerald-100 transition hover:bg-emerald-900/40 disabled:opacity-40"
          >
            {busy ? "Conectando…" : "Conectar mi WhatsApp"}
          </button>
          {!canAdvanceFrom3 ? (
            <p className="flex items-center gap-1.5 text-xs text-amber-300/90">
              <Circle className="h-3 w-3" />
              Completa la clave y el ID del paso 3 antes de conectar.
            </p>
          ) : null}
        </section>
      ) : null}

      {error ? (
        <p className="rounded border border-red-500/40 bg-red-950/30 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          disabled={step <= 1 || busy}
          onClick={() => setStep((s) => Math.max(1, s - 1))}
          className="inline-flex items-center gap-1 rounded border border-cyan-800/60 px-3 py-2 text-xs text-cyan-200 disabled:opacity-30"
        >
          <ChevronLeft className="h-4 w-4" />
          Atrás
        </button>
        {step < 4 ? (
          <button
            type="button"
            disabled={busy || (step === 3 && !canAdvanceFrom3)}
            onClick={() => setStep((s) => Math.min(4, s + 1))}
            className="inline-flex items-center gap-1 rounded border border-cyan-400/50 bg-cyan-950/40 px-4 py-2 text-xs font-semibold text-cyan-100 disabled:opacity-40"
          >
            Continuar
            <ChevronRight className="h-4 w-4" />
          </button>
        ) : null}
      </div>
    </div>
  );
}
