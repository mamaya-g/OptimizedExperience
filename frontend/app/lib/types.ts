export type PlanAction =
  | "RIDE_STANDBY"
  | "BOOK_LIGHTNING_LANE"
  | "REDEEM_LIGHTNING_LANE"
  | "WATCH_SHOW"
  | "DO_ACTIVITY";

export interface PlanStep {
  node_id: string;
  node_name: string;
  action: PlanAction;
  planned_arrival: string;
  planned_departure: string;
  rationale: string;
  wait_minutes: number;
  service_minutes: number;
}

export interface Plan {
  steps: PlanStep[];
  total_prize: number;
  solver_name: string;
  unscheduled_node_ids: string[];
  unscheduled_mandatory_node_ids: string[];
  disclaimer: string;
}

export interface PlanResponse {
  generated_at: string;
  plan: Plan;
}

export type Objective = "maximize_prize" | "all_rides_challenge";

export type NodeKind = "ATTRACTION" | "SHOW" | "ACTIVITY";
export type ShowCategory = "PARADE" | "NIGHTTIME_SPECTACULAR" | "OTHER";
export type LightningLaneType = "MULTI" | "SINGLE" | "NONE";

export interface TimeWindow {
  start: string;
  end: string;
}

export interface PriceInfo {
  amount: number;
  currency: string;
  formatted: string;
}

export interface AttractionListing {
  id: string;
  name: string;
  kind: NodeKind;
  land: string | null;
  show_category: ShowCategory | null;
  wait_minutes: number;
  duration_minutes: number;
  lightning_lane_type: LightningLaneType;
  lightning_lane_window: TimeWindow | null;
  lightning_lane_price: PriceInfo | null;
  time_windows: TimeWindow[];
}

export interface AttractionsResponse {
  generated_at: string;
  attractions: AttractionListing[];
}

// --- Guest preferences (mirrors backend data/preferences.py::Preferences) ---

export type PreferenceTier = "MUST_GO" | "NICE_TO_HAVE" | "SKIP";
export type WaterRideComfort = "MIND_IF_COOL" | "DONT_MIND" | "PREFER_AFTERNOON";
export type WalkingPace = "SLOW" | "AVERAGE" | "FAST";
export type NavigationStrategy = "TIME_OPTIMAL" | "LAND_ORDER" | "CLUSTERED";
export type BlockPlacement = "PREFERRED_RANGE" | "FIXED_TIME" | "SOLVER_CHOICE";
export type ActivityKind = "LUNCH" | "DINNER" | "SHOPPING" | "OTHER";

export interface ActivityBlock {
  name: string;
  duration_minutes: number;
  placement: BlockPlacement;
  kind: ActivityKind;
  range_start: string | null;
  range_end: string | null;
  fixed_time: string | null;
  mandatory: boolean;
}

export interface Preferences {
  water_ride_comfort: WaterRideComfort;
  tiers: Record<string, PreferenceTier>;
  use_lightning_lane: boolean;
  walking_pace: WalkingPace;
  navigation_strategy: NavigationStrategy;
  land_order: string[];
  planned_arrival: string | null;
  planned_departure: string | null;
  activity_blocks: ActivityBlock[];
  // The specific show entity id the guest picked -- not a blanket "any
  // parade" toggle, since a day can run several shows in the same category.
  desired_parade_id: string | null;
  desired_nighttime_show_id: string | null;
  repeat_counts: Record<string, number>;
}

export const DEFAULT_PREFERENCES: Preferences = {
  water_ride_comfort: "MIND_IF_COOL",
  tiers: {},
  use_lightning_lane: true,
  walking_pace: "AVERAGE",
  navigation_strategy: "TIME_OPTIMAL",
  land_order: [],
  planned_arrival: null,
  planned_departure: null,
  activity_blocks: [],
  desired_parade_id: null,
  desired_nighttime_show_id: null,
  repeat_counts: {},
};
