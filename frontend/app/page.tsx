"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { fetchAttractions, fetchPlan } from "./lib/api";
import { hasOnboarded, loadObjective, loadPreferences, saveObjective, savePreferences } from "./lib/storage";
import type { AttractionListing, Objective, Plan, Preferences } from "./lib/types";
import { OnboardingFlow } from "./onboarding/OnboardingFlow";
import { ThreeViewResults } from "./components/ThreeViewResults";

type Stage = "loading" | "onboarding" | "results";

export default function Home() {
  const [stage, setStage] = useState<Stage>("loading");
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [objective, setObjective] = useState<Objective>("maximize_prize");

  const [plan, setPlan] = useState<Plan | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [attractions, setAttractions] = useState<AttractionListing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();

  const runPlan = useCallback((prefs: Preferences, obj: Objective) => {
    startTransition(async () => {
      try {
        const [planRes, attractionsRes] = await Promise.all([fetchPlan(obj, prefs), fetchAttractions()]);
        setPlan(planRes.plan);
        setGeneratedAt(planRes.generated_at);
        setAttractions(attractionsRes.attractions);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    });
  }, []);

  useEffect(() => {
    const prefs = loadPreferences();
    const obj = loadObjective();
    const onboarded = hasOnboarded();
    startTransition(() => {
      setPreferences(prefs);
      setObjective(obj);
      setStage(onboarded ? "results" : "onboarding");
    });
    if (onboarded) runPlan(prefs, obj);
  }, [runPlan]);

  function handleOnboardingComplete(nextPreferences: Preferences, nextObjective: Objective) {
    savePreferences(nextPreferences);
    saveObjective(nextObjective);
    setPreferences(nextPreferences);
    setObjective(nextObjective);
    setStage("results");
    runPlan(nextPreferences, nextObjective);
  }

  function handleReoptimize(nextPreferences: Preferences) {
    savePreferences(nextPreferences);
    setPreferences(nextPreferences);
    runPlan(nextPreferences, objective);
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0a1e3f] via-[#0f2a52] to-[#0a1e3f] text-white">
      <main className="mx-auto max-w-2xl px-4">
        {stage !== "onboarding" && (
          <header className="pt-10 pb-2 text-center sm:pt-14">
            <p className="text-xs uppercase tracking-[0.2em] text-amber-300/80">Disneyland, one day</p>
            <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Optimized Experience</h1>
            <p className="mt-2 text-sm text-white/50">
              Your companion for planning a great day at the park, built around what matters to you.
            </p>
          </header>
        )}

        <div className="pb-14">
          {stage === "loading" && <CenteredMessage text="Loading…" />}

          {stage === "onboarding" && preferences && (
            <OnboardingFlow
              initialPreferences={preferences}
              initialObjective={objective}
              onComplete={handleOnboardingComplete}
            />
          )}

          {stage === "results" && (
            <div className="pt-8">
              {busy && !plan && <CenteredMessage text="Fetching live Disneyland data and planning your day…" />}
              {error && !plan && <ErrorState message={error} />}
              {plan && preferences && (
                <ThreeViewResults
                  plan={plan}
                  generatedAt={generatedAt ?? new Date().toISOString()}
                  attractions={attractions}
                  preferences={preferences}
                  onReoptimize={handleReoptimize}
                  onEditPreferences={() => setStage("onboarding")}
                  refreshing={busy}
                />
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

function CenteredMessage({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-white/50">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-amber-300" />
      <p className="text-sm">{text}</p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-5 py-4 text-sm text-rose-100">
      <p className="font-semibold">Couldn&apos;t load your plan.</p>
      <p className="mt-1 text-rose-200/80">{message}</p>
    </div>
  );
}
