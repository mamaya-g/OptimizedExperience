"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { planStepsToManualItems } from "../lib/manualSchedule";
import { nudgePreferencesFromManualEdits, scheduleableStepIds } from "../lib/nudge";
import { loadCompletedStepIds, saveCompletedStepIds } from "../lib/storage";
import type { AttractionListing, Plan, Preferences } from "../lib/types";
import { ManualScheduleView } from "./ManualScheduleView";
import { StepCard } from "./StepCard";

const TABS = ["Optimized", "Adjust", "Build Your Own"] as const;
const AUTO_REFRESH_MS = 120_000; // matches the backend's ~2min live-data cache

export function ThreeViewResults({
  plan,
  generatedAt,
  attractions,
  preferences,
  onReoptimize,
  onEditPreferences,
  refreshing,
}: {
  plan: Plan;
  generatedAt: string;
  attractions: AttractionListing[];
  preferences: Preferences;
  onReoptimize: (nextPreferences: Preferences) => void;
  onEditPreferences: () => void;
  refreshing: boolean;
}) {
  const [tab, setTab] = useState(0);
  const touchStartX = useRef<number | null>(null);

  const attractionsById = useMemo(() => new Map(attractions.map((a) => [a.id, a])), [attractions]);
  const startTime = useMemo(
    () => (plan.steps[0] ? new Date(plan.steps[0].planned_arrival) : new Date()),
    [plan.steps],
  );

  const [viewBItems, setViewBItems] = useState<AttractionListing[]>(() =>
    planStepsToManualItems(plan.steps, attractionsById),
  );
  const [viewCItems, setViewCItems] = useState<AttractionListing[]>([]);
  const originalIdsRef = useRef(scheduleableStepIds(plan));

  // Re-seed View B only when a *new* solved plan actually arrives (fresh
  // planned_arrival timestamp on step 1) -- not on every render, so it
  // doesn't clobber the guest's in-progress manual edits.
  const planSignature = plan.steps[0]?.planned_arrival ?? "";
  const lastSignature = useRef(planSignature);
  useEffect(() => {
    if (planSignature !== lastSignature.current) {
      lastSignature.current = planSignature;
      setViewBItems(planStepsToManualItems(plan.steps, attractionsById));
      originalIdsRef.current = scheduleableStepIds(plan);
    }
  }, [planSignature, plan, attractionsById]);

  useEffect(() => {
    if (tab !== 0) return;
    const id = setInterval(() => onReoptimize(preferences), AUTO_REFRESH_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  function handleTouchStart(e: React.TouchEvent) {
    touchStartX.current = e.touches[0].clientX;
  }
  function handleTouchEnd(e: React.TouchEvent) {
    if (touchStartX.current === null) return;
    const delta = e.changedTouches[0].clientX - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(delta) < 50) return;
    setTab((t) => Math.min(TABS.length - 1, Math.max(0, t + (delta < 0 ? 1 : -1))));
  }

  function handleReoptimizeFromB() {
    const currentIds = new Set(viewBItems.filter((i) => i.kind !== "ACTIVITY").map((i) => i.id));
    const nudged = nudgePreferencesFromManualEdits(preferences, originalIdsRef.current, currentIds);
    onReoptimize(nudged);
  }

  return (
    <div>
      <div className="mb-5 flex items-center justify-between gap-3">
        <div className="flex gap-1 rounded-full border border-white/10 bg-white/5 p-1">
          {TABS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => setTab(i)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition sm:px-4 sm:text-sm ${
                tab === i ? "bg-amber-300 text-[#0a1e3f]" : "text-white/50 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button type="button" onClick={onEditPreferences} className="shrink-0 text-xs text-white/40 underline underline-offset-4 hover:text-white/70">
          Edit preferences
        </button>
      </div>

      <div data-swipe-region onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
        {tab === 0 && <OptimizedView plan={plan} generatedAt={generatedAt} attractionsById={attractionsById} refreshing={refreshing} />}
        {tab === 1 && (
          <>
            <p className="mb-4 text-sm text-white/60">
              Reorder, remove, or add attractions freely. We&apos;ll flag anything that no longer lines up with a
              showtime or Lightning Lane window, but we won&apos;t stop you.
            </p>
            <ManualScheduleView
              items={viewBItems}
              onItemsChange={setViewBItems}
              attractions={attractions}
              startTime={startTime}
              emptyHint="Nothing scheduled — add something below."
            />
            <button
              type="button"
              onClick={handleReoptimizeFromB}
              disabled={refreshing}
              className="mt-5 w-full rounded-xl bg-white/10 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-white/15 disabled:opacity-50"
            >
              {refreshing ? "Re-optimizing…" : "Re-optimize from here"}
            </button>
          </>
        )}
        {tab === 2 && (
          <>
            <p className="mb-4 text-sm text-white/60">Start from scratch and build your own day, step by step.</p>
            <ManualScheduleView
              items={viewCItems}
              onItemsChange={setViewCItems}
              attractions={attractions}
              startTime={startTime}
              emptyHint="Add your first attraction below to get started."
            />
          </>
        )}
      </div>
    </div>
  );
}

function OptimizedView({
  plan,
  generatedAt,
  attractionsById,
  refreshing,
}: {
  plan: Plan;
  generatedAt: string;
  attractionsById: Map<string, AttractionListing>;
  refreshing: boolean;
}) {
  const unscheduled = plan.unscheduled_node_ids
    .map((id) => attractionsById.get(id))
    .filter((a): a is AttractionListing => Boolean(a));
  const unscheduledMandatory = plan.unscheduled_mandatory_node_ids.map(
    (id) => attractionsById.get(id)?.name ?? id,
  );

  const [completed, setCompleted] = useState<Set<string>>(() => new Set(loadCompletedStepIds()));

  function toggleDone(nodeId: string) {
    setCompleted((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      saveCompletedStepIds([...next]);
      return next;
    });
  }

  return (
    <>
      <p className="mb-1 text-xs text-white/40">
        Updated {new Date(generatedAt).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
        {refreshing && " · refreshing…"}
      </p>
      <p className="mb-4 text-xs text-white/30">Tap anything you&apos;ve already done to check it off.</p>

      {unscheduledMandatory.length > 0 && (
        <div className="mb-6 rounded-xl border border-rose-400/40 bg-rose-500/10 px-5 py-3 text-sm text-rose-100">
          ⚠ Couldn&apos;t fit everything you asked for today: {unscheduledMandatory.join(", ")}.
        </div>
      )}

      {plan.steps.length === 0 ? (
        <p className="py-10 text-center text-white/50">No plan could be generated for today.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {plan.steps.map((step, i) => (
            <StepCard
              key={`${step.node_id}-${i}`}
              time={step.planned_arrival}
              name={step.node_name}
              land={attractionsById.get(step.node_id)?.land ?? null}
              action={step.action}
              waitMinutes={step.wait_minutes}
              durationMinutes={step.service_minutes}
              rationale={step.guest_rationale}
              done={completed.has(step.node_id)}
              onToggleDone={() => toggleDone(step.node_id)}
            />
          ))}
        </ol>
      )}

      {unscheduled.length > 0 && (
        <div className="mt-6 rounded-xl border border-white/10 bg-white/5 px-5 py-4">
          <p className="text-sm font-semibold text-white">Didn&apos;t make today&apos;s plan</p>
          <p className="mt-1 text-xs text-white/50">
            Switch to the Adjust tab to swap any of these into your day.
          </p>
          <ul className="mt-3 flex flex-wrap gap-2">
            {unscheduled.map((a) => (
              <li key={a.id} className="rounded-full bg-white/10 px-3 py-1 text-xs text-white/70">
                {a.name}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-8 text-center text-xs leading-relaxed text-white/30">{plan.disclaimer}</p>
    </>
  );
}
