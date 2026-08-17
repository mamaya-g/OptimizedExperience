import { DEFAULT_PREFERENCES, type Objective, type Preferences } from "./types";

const PREFERENCES_KEY = "oe:preferences";
const ONBOARDED_KEY = "oe:onboarded";
const OBJECTIVE_KEY = "oe:objective";
const COMPLETED_STEPS_KEY = "oe:completed_steps";

export function loadPreferences(): Preferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(PREFERENCES_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    return { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function savePreferences(preferences: Preferences): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  window.localStorage.setItem(ONBOARDED_KEY, "true");
}

export function hasOnboarded(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(ONBOARDED_KEY) === "true";
}

export function loadObjective(): Objective {
  if (typeof window === "undefined") return "maximize_prize";
  const raw = window.localStorage.getItem(OBJECTIVE_KEY);
  return raw === "all_rides_challenge" ? "all_rides_challenge" : "maximize_prize";
}

export function saveObjective(objective: Objective): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(OBJECTIVE_KEY, objective);
}

export function loadCompletedStepIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(COMPLETED_STEPS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveCompletedStepIds(ids: string[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(COMPLETED_STEPS_KEY, JSON.stringify(ids));
}
