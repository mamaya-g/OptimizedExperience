import type { ReactNode } from "react";
import type { PlanAction } from "../lib/types";

const ACTION_STYLE: Record<PlanAction, { label: string; dot: string; border: string }> = {
  RIDE_STANDBY: { label: "Standby line", dot: "bg-sky-400", border: "border-sky-400/40" },
  BOOK_LIGHTNING_LANE: { label: "Book Lightning Lane", dot: "bg-amber-300", border: "border-amber-300/30" },
  REDEEM_LIGHTNING_LANE: { label: "Lightning Lane", dot: "bg-amber-400", border: "border-amber-400/50" },
  WATCH_SHOW: { label: "Show", dot: "bg-violet-300", border: "border-violet-300/40" },
  DO_ACTIVITY: { label: "Break", dot: "bg-emerald-300", border: "border-emerald-300/40" },
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function formatMinutes(minutes: number): string {
  return minutes < 1 ? "<1 min" : `${Math.round(minutes)} min`;
}

export function StepCard({
  time,
  name,
  land,
  action,
  waitMinutes,
  durationMinutes,
  conflictReason,
  trailing,
}: {
  time: string;
  name: string;
  land?: string | null;
  action?: PlanAction;
  waitMinutes: number;
  durationMinutes: number;
  conflictReason?: string | null;
  trailing?: ReactNode;
}) {
  const style = action ? ACTION_STYLE[action] : { label: land ?? "", dot: "bg-white/30", border: "border-white/10" };

  return (
    <li className={`relative rounded-xl border bg-white/5 backdrop-blur-sm px-5 py-4 shadow-sm ${style.border}`}>
      <div className="flex items-start gap-4">
        <div className="flex shrink-0 flex-col items-center pt-0.5 w-16">
          <span className="text-sm font-semibold text-amber-100/90 tabular-nums">{formatTime(time)}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${style.dot}`} aria-hidden />
            <span className="text-[11px] uppercase tracking-wide text-white/50">{style.label}</span>
            {land && action && <span className="text-[11px] text-white/30">· {land}</span>}
          </div>
          <h3 className="mt-0.5 text-base font-semibold text-white">{name}</h3>
          <p className="mt-1 text-sm text-white/60">
            {waitMinutes > 0 && <>~{Math.round(waitMinutes)} min wait</>}
            {waitMinutes > 0 && durationMinutes > 0 && " · "}
            {durationMinutes > 0 && <>{formatMinutes(durationMinutes)} long</>}
          </p>
          {conflictReason && (
            <p className="mt-1.5 rounded-md bg-rose-500/10 px-2 py-1 text-xs text-rose-200">⚠ {conflictReason}</p>
          )}
        </div>
        {trailing && <div className="flex shrink-0 items-center gap-1">{trailing}</div>}
      </div>
    </li>
  );
}
