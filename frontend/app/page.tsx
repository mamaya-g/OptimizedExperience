"use client";

import { useEffect, useState, useTransition } from "react";
import { fetchPlan } from "./lib/api";
import type { Objective, PlanResponse, SolverName } from "./lib/types";
import { ItineraryCard } from "./components/ItineraryCard";

const OBJECTIVES: { value: Objective; label: string }[] = [
  { value: "maximize_prize", label: "Maximize Prize" },
  { value: "all_rides_challenge", label: "All Rides Challenge" },
];

const SOLVERS: { value: SolverName; label: string }[] = [
  { value: "greedy", label: "Greedy (fast heuristic)" },
  { value: "ortools", label: "OR-Tools (global search)" },
];

export default function Home() {
  const [objective, setObjective] = useState<Objective>("maximize_prize");
  const [solver, setSolver] = useState<SolverName>("greedy");
  const [data, setData] = useState<PlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;
    startTransition(async () => {
      try {
        const res = await fetchPlan(objective, solver);
        if (cancelled) return;
        setData(res);
        setError(null);
      } catch (err: unknown) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [objective, solver]);

  const plan = data?.plan;

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0b0a1f] via-[#1a1533] to-[#0b0a1f] text-white">
      <main className="mx-auto max-w-2xl px-4 py-10 sm:py-14">
        <header className="mb-8 text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-amber-300/80">Disneyland, one day</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Optimized Experience</h1>
          <p className="mt-2 text-sm text-white/50">
            A live, algorithm-planned itinerary — not a clone of the Disneyland app.
          </p>
        </header>

        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Select label="Goal" value={objective} onChange={(v) => setObjective(v as Objective)} options={OBJECTIVES} />
          <Select label="Solver" value={solver} onChange={(v) => setSolver(v as SolverName)} options={SOLVERS} />
        </div>

        {loading && <LoadingState />}
        {!loading && error && <ErrorState message={error} />}
        {!loading && !error && plan && data && <PlanView data={data} />}
      </main>
    </div>
  );
}

function Select<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (value: string) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <label className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm">
      <span className="text-white/50">{label}</span>
      <select
        className="bg-transparent font-medium text-white outline-none [&>option]:bg-[#1a1533]"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-white/50">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/20 border-t-amber-300" />
      <p className="text-sm">Fetching live Disneyland data and solving your day…</p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-5 py-4 text-sm text-rose-100">
      <p className="font-semibold">Couldn&apos;t load a plan.</p>
      <p className="mt-1 text-rose-200/80">{message}</p>
    </div>
  );
}

function PlanView({ data }: { data: PlanResponse }) {
  const { plan, generated_at } = data;
  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 px-5 py-4">
        <div>
          <p className="text-xs text-white/40">
            Generated {new Date(generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
          </p>
          <p className="text-sm text-white/60">
            Solver: <span className="font-medium text-white/80">{plan.solver_name}</span>
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold text-amber-300">{plan.total_prize.toFixed(0)}</p>
          <p className="text-xs text-white/40">total prize</p>
        </div>
      </div>

      {plan.unscheduled_mandatory_node_ids.length > 0 && (
        <div className="mb-6 rounded-xl border border-rose-400/40 bg-rose-500/10 px-5 py-3 text-sm text-rose-100">
          ⚠ Could not fit {plan.unscheduled_mandatory_node_ids.length} mandatory block(s) into today&apos;s plan.
        </div>
      )}

      {plan.steps.length === 0 ? (
        <p className="py-10 text-center text-white/50">No plan could be generated for today.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {plan.steps.map((step, i) => (
            <ItineraryCard key={`${step.node_id}-${i}`} step={step} index={i} />
          ))}
        </ol>
      )}

      {plan.unscheduled_node_ids.length > 0 && (
        <p className="mt-6 text-center text-xs text-white/40">
          {plan.unscheduled_node_ids.length} lower-priority attraction(s) didn&apos;t fit today.
        </p>
      )}

      <p className="mt-8 text-center text-xs leading-relaxed text-white/30">{plan.disclaimer}</p>
    </>
  );
}
