import {
  CED_PRIVACY_INCLUDED_HIGHLIGHT,
  CED_PRIVACY_PLAN_BADGE,
} from "@ced/types";

type PlanHighlightListProps = {
  highlights: readonly string[];
  /** Slightly smaller text (dashboard / overlays) */
  compact?: boolean;
};

export function isCedPrivacyPlanHighlight(text: string): boolean {
  return text === CED_PRIVACY_INCLUDED_HIGHLIGHT;
}

export function PlanHighlightList({
  highlights,
  compact = false,
}: PlanHighlightListProps) {
  const textSize = compact ? "text-[11px]" : "text-xs";
  const badgeSize = compact ? "text-[8px]" : "text-[9px]";

  return (
    <ul className={`space-y-1.5 ${textSize} text-cyan-100/75`}>
      {highlights.map((h) =>
        isCedPrivacyPlanHighlight(h) ? (
          <li key={h} className="list-none py-0.5">
            <span
              className={`inline-flex flex-wrap items-center gap-1.5 rounded-md border border-violet-400/50 bg-violet-950/50 px-2 py-1 shadow-[0_0_14px_rgba(139,92,246,0.35)] ${compact ? "w-full" : ""}`}
            >
              <span
                className={`font-[family-name:var(--font-orbitron)] ${badgeSize} font-bold tracking-[0.2em] text-violet-200`}
              >
                {CED_PRIVACY_PLAN_BADGE}
              </span>
              <span className="text-violet-100/90">· verificable incluida</span>
            </span>
          </li>
        ) : (
          <li key={h}>· {h}</li>
        ),
      )}
    </ul>
  );
}
