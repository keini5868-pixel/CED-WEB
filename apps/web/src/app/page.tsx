import Link from "next/link";
import {
  CED_ELITE_FEATURES,
  FOUNDING_MEMBER_MAX_SLOTS,
  PLAN_PRICES_USD,
  RECHARGE_QUICK_AMOUNTS_USD,
  quoteRecharge,
} from "@ced/types";

export default function HomePage() {
  const foundingPrice = PLAN_PRICES_USD.elite_founding;
  const regularPrice = PLAN_PRICES_USD.elite_regular;

  return (
    <main className="relative min-h-screen overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{
          background:
            "radial-gradient(ellipse at 50% 40%, rgba(0,229,255,0.15) 0%, transparent 60%)",
        }}
      />

      <header className="relative z-10 flex items-center justify-between border-b border-cyan-500/20 px-6 py-4">
        <span className="font-[family-name:var(--font-orbitron)] text-sm tracking-[0.3em] text-cyan-400">
          SYS: ONLINE
        </span>
        <h1 className="font-[family-name:var(--font-orbitron)] text-lg font-bold tracking-widest text-cyan-300 ced-glow-text">
          CED ÉLITE
        </h1>
        <span className="text-xs text-cyan-600">SECURE</span>
      </header>

      <section className="relative z-10 mx-auto flex max-w-3xl flex-col items-center px-6 py-16 text-center">
        <div className="mb-8 flex h-48 w-48 items-center justify-center rounded-full border-2 border-cyan-400/60 ced-glow">
          <span className="font-[family-name:var(--font-orbitron)] text-4xl font-bold text-cyan-300">
            CED
          </span>
        </div>
        <h2 className="font-[family-name:var(--font-orbitron)] text-2xl font-bold tracking-[0.15em] text-cyan-300 md:text-3xl">
          UN SOLO PLAN PREMIUM
        </h2>
        <p className="mt-3 text-sm text-cyan-100/70">
          {CED_ELITE_FEATURES.geminiLiveMinutesPerDay} min/día Gemini Live · Claude
          ilimitado · HUD en vivo · PWA móvil
        </p>

        <div className="mt-10 w-full max-w-lg rounded border border-cyan-400/40 bg-black/50 p-6 text-left ced-glow">
          <p className="font-[family-name:var(--font-orbitron)] text-xs tracking-widest text-amber-400">
            FOUNDING — primeros {FOUNDING_MEMBER_MAX_SLOTS} cupos
          </p>
          <p className="mt-2 font-[family-name:var(--font-orbitron)] text-3xl font-bold text-white">
            ${foundingPrice}
            <span className="text-base font-normal text-cyan-500">/mes</span>
          </p>
          <p className="mt-2 text-xs text-cyan-300/80">
            Precio bloqueado de por vida mientras mantengas la suscripción ·
            Certificado founding member PDF
          </p>
          <p className="mt-4 text-xs text-cyan-600">
            Después del cupo {FOUNDING_MEMBER_MAX_SLOTS}: ${regularPrice}/mes
          </p>
        </div>

        <p className="mt-6 text-xs text-cyan-500">
          7 días gratis · sin tarjeta
        </p>

        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <Link
            href="/signup"
            className="rounded border-2 border-cyan-400 bg-cyan-400/10 px-8 py-3 font-[family-name:var(--font-orbitron)] text-sm font-bold tracking-wider text-cyan-300 transition hover:bg-cyan-400/25"
          >
            EMPEZAR GRATIS
          </Link>
          <Link
            href="/login"
            className="rounded border border-cyan-600 px-8 py-3 text-sm text-cyan-400/90 hover:border-cyan-400"
          >
            INICIAR SESIÓN
          </Link>
        </div>

        <div className="mt-12 w-full max-w-lg rounded border border-cyan-500/20 bg-black/30 p-4 text-left text-xs text-cyan-400/90">
          <p className="font-[family-name:var(--font-orbitron)] tracking-wider text-cyan-300">
            RECARGAS FLEXIBLES
          </p>
          <p className="mt-2">40% margen plataforma · 60% saldo de uso · no expira</p>
          <ul className="mt-3 space-y-1">
            {RECHARGE_QUICK_AMOUNTS_USD.map((amount) => {
              const q = quoteRecharge(amount);
              return (
                <li key={amount}>
                  ${amount} → ${q.clientBalanceUsd} saldo (~{q.estimatedExtraHours}h
                  extra)
                </li>
              );
            })}
          </ul>
        </div>
      </section>
    </main>
  );
}
