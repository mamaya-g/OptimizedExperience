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
export type SolverName = "greedy" | "ortools";
