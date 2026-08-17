import type { AttractionListing, PlanStep, TimeWindow } from "./types";

export interface ManualStep {
  attraction: AttractionListing;
  arrival: Date;
  departure: Date;
  conflict: boolean;
  conflictReason: string | null;
}

function withinAnyWindow(moment: Date, windows: TimeWindow[]): boolean {
  return windows.some((w) => moment >= new Date(w.start) && moment <= new Date(w.end));
}

/** Cumulative-time recompute for the manual (adjustable / build-your-own) views --
 * pure client-side, no backend re-solve. Flags, but never removes, a step whose
 * new slot falls outside its own known showtime or Lightning Lane window, since
 * the guest is deliberately overriding the solver here. */
export function recomputeManualSchedule(items: AttractionListing[], startTime: Date): ManualStep[] {
  let clock = startTime;
  const steps: ManualStep[] = [];

  for (const attraction of items) {
    const arrival = clock;
    const totalMinutes = attraction.wait_minutes + attraction.duration_minutes;
    const departure = new Date(arrival.getTime() + totalMinutes * 60_000);

    let conflict = false;
    let conflictReason: string | null = null;

    if (attraction.kind === "SHOW" && attraction.time_windows.length > 0 && !withinAnyWindow(arrival, attraction.time_windows)) {
      conflict = true;
      conflictReason = "Doesn't line up with any of today's showtimes for this one.";
    } else if (
      attraction.lightning_lane_type !== "NONE" &&
      attraction.lightning_lane_window &&
      !withinAnyWindow(arrival, [attraction.lightning_lane_window])
    ) {
      conflict = true;
      conflictReason = "Outside the current Lightning Lane return window.";
    }

    steps.push({ attraction, arrival, departure, conflict, conflictReason });
    clock = departure;
  }

  return steps;
}

/** Seeds View B (Adjustable) from a solved plan. Most steps map straight onto
 * the matching /api/attractions row (real wait/duration/LL data); a step with
 * no match (a meal/shopping break, which the attractions endpoint never lists)
 * gets a minimal synthetic entry built from the plan step itself, so the whole
 * day -- breaks included -- is reorderable through the one shared mechanism. */
export function planStepsToManualItems(
  steps: PlanStep[],
  attractionsById: Map<string, AttractionListing>,
): AttractionListing[] {
  return steps.map((step) => {
    const match = attractionsById.get(step.node_id);
    if (match) return match;
    return {
      id: step.node_id,
      name: step.node_name,
      kind: "ACTIVITY",
      land: null,
      show_category: null,
      wait_minutes: 0,
      duration_minutes: step.service_minutes,
      lightning_lane_type: "NONE",
      lightning_lane_window: null,
      lightning_lane_price: null,
      time_windows: [],
    };
  });
}
