import type { Objective, PlanResponse, SolverName } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function fetchPlan(objective: Objective, solver: SolverName): Promise<PlanResponse> {
  const url = `${API_BASE}/api/plan?objective=${objective}&solver=${solver}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body?.detail ?? "";
    } catch {
      // ignore, fall back to statusText below
    }
    throw new Error(detail || `Request failed (${res.status} ${res.statusText})`);
  }
  return res.json();
}
