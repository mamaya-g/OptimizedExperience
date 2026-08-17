"use client";

import { useMemo } from "react";
import type { AttractionListing, PreferenceTier } from "../lib/types";

const TIER_OPTIONS: { value: PreferenceTier; label: string }[] = [
  { value: "MUST_GO", label: "Must-see" },
  { value: "NICE_TO_HAVE", label: "Would like" },
  { value: "SKIP", label: "Skip" },
];

function formatDuration(minutes: number): string {
  return minutes < 1 ? "<1 min" : `${Math.round(minutes)} min`;
}

export function AttractionPicker({
  attractions,
  tiers,
  onChangeTier,
  repeatCounts,
  onChangeRepeatCount,
}: {
  attractions: AttractionListing[];
  tiers: Record<string, PreferenceTier>;
  onChangeTier: (id: string, tier: PreferenceTier | null) => void;
  repeatCounts: Record<string, number>;
  onChangeRepeatCount: (id: string, count: number) => void;
}) {
  const rides = useMemo(() => attractions.filter((a) => a.kind === "ATTRACTION"), [attractions]);

  const byLand = useMemo(() => {
    const groups = new Map<string, AttractionListing[]>();
    for (const ride of rides) {
      const land = ride.land ?? "Other";
      if (!groups.has(land)) groups.set(land, []);
      groups.get(land)!.push(ride);
    }
    for (const list of groups.values()) list.sort((a, b) => a.name.localeCompare(b.name));
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [rides]);

  const mustCount = Object.values(tiers).filter((t) => t === "MUST_GO").length;

  return (
    <div>
      <p className="mb-4 text-sm text-white/60">
        Tag anything you already know you want. Everything else stays available for the plan to fit in
        where it can — you don&apos;t have to rate every ride.
        {mustCount > 0 && <span className="text-amber-200"> {mustCount} marked must-see.</span>}
      </p>
      <div className="flex flex-col gap-3">
        {byLand.map(([land, items]) => (
          <details key={land} className="group rounded-xl border border-white/10 bg-white/5" open>
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-white">
              <span>{land}</span>
              <span className="text-xs font-normal text-white/40">{items.length} attractions</span>
            </summary>
            <ul className="flex flex-col gap-1 px-2 pb-2">
              {items.map((ride) => {
                const tier = tiers[ride.id];
                const wantsThisRide = tier === "MUST_GO" || tier === "NICE_TO_HAVE";
                const count = repeatCounts[ride.id] ?? 1;
                return (
                  <li key={ride.id} className="flex flex-col gap-2 rounded-lg px-2 py-2">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-white">{ride.name}</p>
                        <p className="text-xs text-white/40">
                          {formatDuration(ride.duration_minutes)}
                          {ride.wait_minutes > 0 && <> · ~{Math.round(ride.wait_minutes)} min wait now</>}
                          {ride.lightning_lane_type !== "NONE" && <> · Lightning Lane available</>}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1.5">
                        {TIER_OPTIONS.map((opt) => {
                          const active = tier === opt.value;
                          return (
                            <button
                              key={opt.value}
                              type="button"
                              onClick={() => onChangeTier(ride.id, active ? null : opt.value)}
                              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                                active
                                  ? opt.value === "SKIP"
                                    ? "bg-white/20 text-white"
                                    : "bg-amber-300 text-[#0a1e3f]"
                                  : "bg-white/5 text-white/50 hover:bg-white/10"
                              }`}
                            >
                              {opt.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    {wantsThisRide && (
                      <div className="flex items-center gap-2 text-xs text-white/50 sm:ml-auto sm:justify-end">
                        <span>Ride it more than once?</span>
                        <button
                          type="button"
                          onClick={() => onChangeRepeatCount(ride.id, Math.max(1, count - 1))}
                          disabled={count <= 1}
                          className="rounded-md px-2 py-0.5 text-white/60 hover:bg-white/10 disabled:opacity-30"
                        >
                          −
                        </button>
                        <span className="w-4 text-center text-white">{count}</span>
                        <button
                          type="button"
                          onClick={() => onChangeRepeatCount(ride.id, count + 1)}
                          className="rounded-md px-2 py-0.5 text-white/60 hover:bg-white/10"
                        >
                          +
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
      </div>
    </div>
  );
}
