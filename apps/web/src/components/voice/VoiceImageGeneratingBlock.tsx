"use client";

type Props = {
  title?: string;
  detail?: string;
  compact?: boolean;
};

/** Spinner de imagen en voz — título + subtítulo Centinela. */
export function VoiceImageGeneratingBlock({
  title = "Generando imagen…",
  detail,
  compact = false,
}: Props) {
  return (
    <div className={`flex items-start gap-3 ${compact ? "py-1" : "py-2"}`}>
      <span
        className={`shrink-0 animate-spin rounded-full border-2 border-cyan-300/30 border-t-cyan-300 ${
          compact ? "mt-0.5 h-5 w-5" : "h-6 w-6"
        }`}
      />
      <div className="min-w-0">
        <p
          className={`font-medium text-cyan-100 ${
            compact ? "text-[11px]" : "text-sm"
          }`}
        >
          {title}
        </p>
        {detail ? (
          <p
            className={`mt-1 leading-snug text-cyan-500/90 ${
              compact ? "text-[9px]" : "text-[10px]"
            }`}
          >
            {detail}
          </p>
        ) : null}
      </div>
    </div>
  );
}
