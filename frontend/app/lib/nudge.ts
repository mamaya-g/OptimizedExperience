import type { Plan, Preferences } from "./types";

const SCHEDULEABLE_ACTIONS = new Set(["RIDE_STANDBY", "REDEEM_LIGHTNING_LANE", "WATCH_SHOW"]);

export function scheduleableStepIds(plan: Plan): Set<string> {
  return new Set(plan.steps.filter((s) => SCHEDULEABLE_ACTIONS.has(s.action)).map((s) => s.node_id));
}

/** "Re-optimize from here": turns the guest's manual additions/removals in
 * View B into tier nudges, then hands the algorithm back the wheel -- an
 * attraction they manually added becomes a must-see, one they manually
 * removed gets skipped, everything else keeps its prior tier. */
export function nudgePreferencesFromManualEdits(
  base: Preferences,
  originalIds: Set<string>,
  currentIds: Set<string>,
): Preferences {
  const tiers = { ...base.tiers };
  for (const id of currentIds) {
    if (!originalIds.has(id)) tiers[id] = "MUST_GO";
  }
  for (const id of originalIds) {
    if (!currentIds.has(id)) tiers[id] = "SKIP";
  }
  return { ...base, tiers };
}
