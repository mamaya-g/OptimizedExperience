import type { AttractionsResponse, Objective, PlanResponse, Preferences } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function unwrap<T>(res: Response): Promise<T> {
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

export async function fetchPlan(objective: Objective, preferences: Preferences): Promise<PlanResponse> {
  const url = `${API_BASE}/api/plan?objective=${objective}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(preferences),
    cache: "no-store",
  });
  return unwrap<PlanResponse>(res);
}

export async function fetchAttractions(): Promise<AttractionsResponse> {
  const res = await fetch(`${API_BASE}/api/attractions`, { cache: "no-store" });
  return unwrap<AttractionsResponse>(res);
}
