import type { PlanAction, PlanStep } from "../lib/types";

const ACTION_STYLE: Record<PlanAction, { label: string; dot: string; border: string }> = {
  RIDE_STANDBY: { label: "Standby", dot: "bg-teal-400", border: "border-teal-400/40" },
  BOOK_LIGHTNING_LANE: { label: "Book Lightning Lane", dot: "bg-amber-300", border: "border-amber-300/30" },
  REDEEM_LIGHTNING_LANE: { label: "Lightning Lane", dot: "bg-amber-400", border: "border-amber-400/50" },
  WATCH_SHOW: { label: "Show", dot: "bg-violet-400", border: "border-violet-400/40" },
  DO_ACTIVITY: { label: "Break", dot: "bg-rose-400", border: "border-rose-400/40" },
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function ItineraryCard({ step, index }: { step: PlanStep; index: number }) {
  const style = ACTION_STYLE[step.action];
  return (
    <li
      className={`relative rounded-xl border bg-white/5 backdrop-blur-sm px-5 py-4 shadow-sm ${style.border}`}
    >
      <div className="flex items-start gap-4">
        <div className="flex flex-col items-center pt-0.5 shrink-0 w-16">
          <span className="text-sm font-semibold text-amber-100/90 tabular-nums">
            {formatTime(step.planned_arrival)}
          </span>
          <span className="text-[11px] text-white/40">#{index + 1}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`h-2 w-2 rounded-full ${style.dot}`} aria-hidden />
            <span className="text-[11px] uppercase tracking-wide text-white/50">{style.label}</span>
          </div>
          <h3 className="mt-0.5 text-base font-semibold text-white">{step.node_name}</h3>
          <p className="mt-1 text-sm text-white/60 leading-snug">{step.rationale}</p>
        </div>
      </div>
    </li>
  );
}
