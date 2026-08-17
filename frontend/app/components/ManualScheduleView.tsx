"use client";

import { useMemo, useState } from "react";
import { recomputeManualSchedule } from "../lib/manualSchedule";
import type { AttractionListing } from "../lib/types";
import { StepCard } from "./StepCard";

export function ManualScheduleView({
  items,
  onItemsChange,
  attractions,
  startTime,
  emptyHint,
}: {
  items: AttractionListing[];
  onItemsChange: (items: AttractionListing[]) => void;
  attractions: AttractionListing[];
  startTime: Date;
  emptyHint: string;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const steps = useMemo(() => recomputeManualSchedule(items, startTime), [items, startTime]);
  const currentIds = useMemo(() => new Set(items.map((i) => i.id)), [items]);
  const available = useMemo(
    () => attractions.filter((a) => !currentIds.has(a.id)).sort((a, b) => a.name.localeCompare(b.name)),
    [attractions, currentIds],
  );

  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    onItemsChange(next);
  }

  function remove(index: number) {
    onItemsChange(items.filter((_, i) => i !== index));
  }

  function add(attraction: AttractionListing) {
    onItemsChange([...items, attraction]);
    setPickerOpen(false);
  }

  return (
    <div>
      {steps.length === 0 ? (
        <p className="py-10 text-center text-sm text-white/50">{emptyHint}</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {steps.map((step, i) => (
            <StepCard
              key={`${step.attraction.id}-${i}`}
              time={step.arrival.toISOString()}
              name={step.attraction.name}
              land={step.attraction.land}
              waitMinutes={step.attraction.wait_minutes}
              durationMinutes={step.attraction.duration_minutes}
              conflictReason={step.conflictReason}
              trailing={
                <>
                  <button
                    type="button"
                    onClick={() => move(i, -1)}
                    disabled={i === 0}
                    aria-label="Move earlier"
                    className="rounded-md px-2 py-1 text-white/50 hover:bg-white/10 disabled:opacity-20"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => move(i, 1)}
                    disabled={i === steps.length - 1}
                    aria-label="Move later"
                    className="rounded-md px-2 py-1 text-white/50 hover:bg-white/10 disabled:opacity-20"
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    aria-label="Remove"
                    className="rounded-md px-2 py-1 text-rose-300/70 hover:bg-rose-500/10"
                  >
                    ✕
                  </button>
                </>
              }
            />
          ))}
        </ol>
      )}

      <div className="mt-5">
        <button
          type="button"
          onClick={() => setPickerOpen((o) => !o)}
          className="w-full rounded-xl border border-dashed border-white/20 px-4 py-3 text-sm font-medium text-amber-200 hover:bg-white/5"
        >
          {pickerOpen ? "Close" : "+ Add an attraction"}
        </button>
        {pickerOpen && (
          <ul className="mt-3 flex max-h-80 flex-col gap-1 overflow-y-auto rounded-xl border border-white/10 bg-white/5 p-2">
            {available.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => add(a)}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-white hover:bg-white/10"
                >
                  <span>
                    {a.name}
                    {a.land && <span className="ml-2 text-xs text-white/40">{a.land}</span>}
                  </span>
                  <span className="text-xs text-white/40">+</span>
                </button>
              </li>
            ))}
            {available.length === 0 && <li className="px-3 py-2 text-sm text-white/40">Nothing left to add.</li>}
          </ul>
        )}
      </div>
    </div>
  );
}
