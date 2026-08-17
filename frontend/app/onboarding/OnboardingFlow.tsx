"use client";

import { useEffect, useState, useTransition } from "react";
import { fetchAttractions } from "../lib/api";
import type {
  ActivityBlock,
  ActivityKind,
  AttractionListing,
  Objective,
  PreferenceTier,
  Preferences,
  WalkingPace,
  WaterRideComfort,
} from "../lib/types";
import { AttractionPicker } from "./AttractionPicker";

const STEPS = [
  "Attractions",
  "Meals & shopping",
  "Parades & shows",
  "Water rides",
  "Lightning Lane",
  "Walking pace",
  "Arrival & departure",
] as const;

function combineTodayWithTime(time: string): string {
  const [hours, minutes] = time.split(":").map(Number);
  const d = new Date();
  d.setHours(hours, minutes, 0, 0);
  return d.toISOString();
}

function timeFromIso(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function findBlock(blocks: ActivityBlock[], kind: ActivityKind): ActivityBlock | undefined {
  return blocks.find((b) => b.kind === kind);
}

function upsertBlock(blocks: ActivityBlock[], kind: ActivityKind, block: ActivityBlock | null): ActivityBlock[] {
  const rest = blocks.filter((b) => b.kind !== kind);
  return block ? [...rest, block] : rest;
}

export function OnboardingFlow({
  initialPreferences,
  initialObjective,
  onComplete,
}: {
  initialPreferences: Preferences;
  initialObjective: Objective;
  onComplete: (preferences: Preferences, objective: Objective) => void;
}) {
  const [stepIndex, setStepIndex] = useState(0);
  const [preferences, setPreferences] = useState<Preferences>(initialPreferences);
  const [objective, setObjective] = useState<Objective>(initialObjective);
  const [attractions, setAttractions] = useState<AttractionListing[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, startTransition] = useTransition();

  useEffect(() => {
    startTransition(async () => {
      try {
        const res = await fetchAttractions();
        setAttractions(res.attractions);
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Couldn't load today's attractions.");
      }
    });
  }, []);

  function setTier(id: string, tier: PreferenceTier | null) {
    setPreferences((prev) => {
      const tiers = { ...prev.tiers };
      if (tier) tiers[id] = tier;
      else delete tiers[id];
      // A ride you're no longer marking as wanted shouldn't keep a stale repeat count.
      const repeat_counts = { ...prev.repeat_counts };
      if (!tier || tier === "SKIP") delete repeat_counts[id];
      return { ...prev, tiers, repeat_counts };
    });
  }

  function setRepeatCount(id: string, count: number) {
    setPreferences((prev) => {
      const repeat_counts = { ...prev.repeat_counts };
      if (count <= 1) delete repeat_counts[id];
      else repeat_counts[id] = count;
      return { ...prev, repeat_counts };
    });
  }

  const isLast = stepIndex === STEPS.length - 1;

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:py-14">
      <header className="mb-8 text-center">
        <p className="text-xs uppercase tracking-[0.2em] text-amber-300/80">Before we plan your day</p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">
          Tell us what you&apos;re hoping for
        </h1>
        <p className="mt-2 text-sm text-white/50">Takes about a minute. You can change any of this later.</p>
      </header>

      <ol className="mb-8 flex items-center justify-center gap-1.5">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-1.5">
            <span
              className={`h-1.5 rounded-full transition-all ${
                i === stepIndex ? "w-6 bg-amber-300" : i < stepIndex ? "w-1.5 bg-amber-300/50" : "w-1.5 bg-white/15"
              }`}
            />
          </li>
        ))}
      </ol>
      <p className="mb-6 text-center text-xs font-medium uppercase tracking-wide text-white/40">
        {STEPS[stepIndex]}
      </p>

      <div className="rounded-2xl border border-white/10 bg-white/5 p-5 sm:p-6">
        {stepIndex === 0 && (
          <>
            <ObjectiveChoice objective={objective} onChange={setObjective} />
            <hr className="my-5 border-white/10" />
            {loading && <p className="py-8 text-center text-sm text-white/50">Loading today&apos;s attractions…</p>}
            {loadError && <p className="py-8 text-center text-sm text-rose-200">{loadError}</p>}
            {attractions && (
              <AttractionPicker
                attractions={attractions}
                tiers={preferences.tiers}
                onChangeTier={setTier}
                repeatCounts={preferences.repeat_counts}
                onChangeRepeatCount={setRepeatCount}
              />
            )}
          </>
        )}

        {stepIndex === 1 && <MealsAndShopping preferences={preferences} setPreferences={setPreferences} />}

        {stepIndex === 2 && (
          <ParadesAndShows preferences={preferences} setPreferences={setPreferences} attractions={attractions ?? []} />
        )}

        {stepIndex === 3 && <WaterRideStep preferences={preferences} setPreferences={setPreferences} />}

        {stepIndex === 4 && <LightningLaneExplainer preferences={preferences} setPreferences={setPreferences} />}

        {stepIndex === 5 && <WalkingPaceStep preferences={preferences} setPreferences={setPreferences} />}

        {stepIndex === 6 && <ArrivalDepartureStep preferences={preferences} setPreferences={setPreferences} />}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setStepIndex((i) => Math.max(0, i - 1))}
          disabled={stepIndex === 0}
          className="rounded-lg px-4 py-2 text-sm font-medium text-white/60 disabled:opacity-0"
        >
          Back
        </button>
        <button
          type="button"
          onClick={() => (isLast ? onComplete(preferences, objective) : setStepIndex((i) => i + 1))}
          className="rounded-lg bg-amber-300 px-6 py-2.5 text-sm font-semibold text-[#0a1e3f] shadow-sm transition hover:bg-amber-200"
        >
          {isLast ? "Plan my day" : "Next"}
        </button>
      </div>
    </div>
  );
}

function ObjectiveChoice({ objective, onChange }: { objective: Objective; onChange: (o: Objective) => void }) {
  return (
    <div>
      <p className="mb-3 text-sm font-semibold text-white">What matters more today?</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <ChoiceCard
          selected={objective === "maximize_prize"}
          onClick={() => onChange("maximize_prize")}
          title="Hit my top picks efficiently"
          body="Prioritizes your must-sees and favorites, fitting in extras where there's time."
        />
        <ChoiceCard
          selected={objective === "all_rides_challenge"}
          onClick={() => onChange("all_rides_challenge")}
          title="Try to ride everything"
          body="Aims to cover as many attractions as possible across the whole day."
        />
      </div>
    </div>
  );
}

function ChoiceCard({
  selected,
  onClick,
  title,
  body,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  body: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl border px-4 py-3 text-left transition ${
        selected ? "border-amber-300 bg-amber-300/10" : "border-white/10 bg-white/5 hover:bg-white/10"
      }`}
    >
      <p className={`text-sm font-semibold ${selected ? "text-amber-200" : "text-white"}`}>{title}</p>
      <p className="mt-1 text-xs text-white/50">{body}</p>
    </button>
  );
}

function MealsAndShopping({
  preferences,
  setPreferences,
}: {
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
}) {
  return (
    <div className="flex flex-col gap-6">
      <MealBlockEditor
        kind="LUNCH"
        title="Lunch"
        defaultDuration={45}
        preferences={preferences}
        setPreferences={setPreferences}
      />
      <MealBlockEditor
        kind="DINNER"
        title="Dinner"
        defaultDuration={60}
        preferences={preferences}
        setPreferences={setPreferences}
      />
      <MealBlockEditor
        kind="SHOPPING"
        title="Shopping time"
        defaultDuration={30}
        preferences={preferences}
        setPreferences={setPreferences}
      />
    </div>
  );
}

function MealBlockEditor({
  kind,
  title,
  defaultDuration,
  preferences,
  setPreferences,
}: {
  kind: ActivityKind;
  title: string;
  defaultDuration: number;
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
}) {
  const block = findBlock(preferences.activity_blocks, kind);
  const enabled = Boolean(block);
  const hasSpecificTime = block?.placement === "PREFERRED_RANGE";

  function update(next: Partial<ActivityBlock> | null) {
    setPreferences((prev) => ({
      ...prev,
      activity_blocks: upsertBlock(
        prev.activity_blocks,
        kind,
        next === null
          ? null
          : {
              name: title,
              duration_minutes: defaultDuration,
              placement: "SOLVER_CHOICE",
              kind,
              range_start: null,
              range_end: null,
              fixed_time: null,
              mandatory: true,
              ...findBlock(prev.activity_blocks, kind),
              ...next,
            },
      ),
    }));
  }

  return (
    <div>
      <label className="flex items-center gap-3">
        <input type="checkbox" checked={enabled} onChange={(e) => update(e.target.checked ? {} : null)} className="h-4 w-4" />
        <span className="text-sm font-semibold text-white">{title}</span>
      </label>
      {enabled && (
        <div className="mt-3 ml-7 flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm text-white/70">
            <input
              type="radio"
              checked={!hasSpecificTime}
              onChange={() => update({ placement: "SOLVER_CHOICE", range_start: null, range_end: null })}
            />
            Let the plan pick a time
          </label>
          <label className="flex items-center gap-2 text-sm text-white/70">
            <input
              type="radio"
              checked={hasSpecificTime}
              onChange={() =>
                update({
                  placement: "PREFERRED_RANGE",
                  range_start: combineTodayWithTime("12:00"),
                  range_end: combineTodayWithTime("13:30"),
                })
              }
            />
            Around a specific time
          </label>
          {hasSpecificTime && (
            <div className="ml-6 flex items-center gap-2 text-sm">
              <input
                type="time"
                value={timeFromIso(block!.range_start)}
                onChange={(e) => update({ range_start: combineTodayWithTime(e.target.value) })}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white"
              />
              <span className="text-white/40">to</span>
              <input
                type="time"
                value={timeFromIso(block!.range_end)}
                onChange={(e) => update({ range_end: combineTodayWithTime(e.target.value) })}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatShowTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function ParadesAndShows({
  preferences,
  setPreferences,
  attractions,
}: {
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
  attractions: AttractionListing[];
}) {
  const parades = attractions.filter((a) => a.show_category === "PARADE");
  const nightShows = attractions.filter((a) => a.show_category === "NIGHTTIME_SPECTACULAR");

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-white/60">
        Pick a specific one if you&apos;ve got your eye on it — we&apos;ll build the day around it. If it truly
        can&apos;t fit, we&apos;ll tell you honestly instead of just dropping it silently.
      </p>
      <ShowPicker
        title="Want to catch a parade?"
        options={parades}
        selectedId={preferences.desired_parade_id}
        onSelect={(id) => setPreferences((p) => ({ ...p, desired_parade_id: id }))}
        emptyText="No parade scheduled today."
      />
      <ShowPicker
        title="Want to catch a nighttime show?"
        options={nightShows}
        selectedId={preferences.desired_nighttime_show_id}
        onSelect={(id) => setPreferences((p) => ({ ...p, desired_nighttime_show_id: id }))}
        emptyText="No nighttime show scheduled today."
      />
    </div>
  );
}

function ShowPicker({
  title,
  options,
  selectedId,
  onSelect,
  emptyText,
}: {
  title: string;
  options: AttractionListing[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  emptyText: string;
}) {
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-white">{title}</p>
      {options.length === 0 ? (
        <p className="text-sm text-white/40">{emptyText}</p>
      ) : (
        <div className="flex flex-col gap-2">
          <ChoiceCard selected={selectedId === null} onClick={() => onSelect(null)} title="Not today" body="Skip this one." />
          {options.map((opt) => (
            <ChoiceCard
              key={opt.id}
              selected={selectedId === opt.id}
              onClick={() => onSelect(opt.id)}
              title={opt.name}
              body={
                opt.time_windows.length > 0
                  ? opt.time_windows.map((w) => formatShowTime(w.start)).join(" · ")
                  : "Showtime not yet announced."
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LightningLaneExplainer({
  preferences,
  setPreferences,
}: {
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-white/70">
        <p className="font-semibold text-white">Multi Pass</p>
        <p className="mt-1">
          You hold one active reservation at a time — book a return window for a ride, use it, then book the
          next one. Roughly $34+ per person, per day.
        </p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-white/70">
        <p className="font-semibold text-white">Single Pass</p>
        <p className="mt-1">
          Pay per ride for a small number of headliner attractions, once each. Priced individually — we&apos;ll
          show the real price where it&apos;s available.
        </p>
      </div>
      <ToggleRow
        title="Use Lightning Lane in my plan"
        checked={preferences.use_lightning_lane}
        onChange={(v) => setPreferences((p) => ({ ...p, use_lightning_lane: v }))}
      />
    </div>
  );
}

function ToggleRow({ title, checked, onChange }: { title: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-4 py-3">
      <span className="text-sm font-medium text-white">{title}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 rounded-full transition ${checked ? "bg-amber-300" : "bg-white/15"}`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
            checked ? "translate-x-5" : "translate-x-0.5"
          }`}
        />
      </button>
    </label>
  );
}

const WATER_RIDE_OPTIONS: { value: WaterRideComfort; title: string; body: string }[] = [
  { value: "DONT_MIND", title: "Ride them anytime", body: "Don't work around the weather — schedule water rides whenever they fit best." },
  {
    value: "MIND_IF_COOL",
    title: "Skip them if it's cool or cloudy",
    body: "Avoid scheduling water rides during cooler, overcast stretches of the day.",
  },
  {
    value: "PREFER_AFTERNOON",
    title: "Only in the afternoon",
    body: "Only schedule water rides once it's warmed up later in the day.",
  },
];

function WaterRideStep({
  preferences,
  setPreferences,
}: {
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
}) {
  return (
    <div>
      <p className="mb-4 text-sm text-white/60">
        Rides like Grizzly River Run are a lot less fun when it&apos;s cold or overcast. We check the day&apos;s
        forecast — tell us how you feel about the timing.
      </p>
      <div className="flex flex-col gap-3">
        {WATER_RIDE_OPTIONS.map((opt) => (
          <ChoiceCard
            key={opt.value}
            selected={preferences.water_ride_comfort === opt.value}
            onClick={() => setPreferences((p) => ({ ...p, water_ride_comfort: opt.value }))}
            title={opt.title}
            body={opt.body}
          />
        ))}
      </div>
    </div>
  );
}

const WALKING_PACE_OPTIONS: { value: WalkingPace; label: string; body: string }[] = [
  { value: "SLOW", label: "Relaxed", body: "More time between attractions, less rushing." },
  { value: "AVERAGE", label: "Average", body: "A comfortable, typical pace." },
  { value: "FAST", label: "Brisk", body: "Cover more ground, less time spent walking." },
];

function WalkingPaceStep({
  preferences,
  setPreferences,
}: {
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
}) {
  return (
    <div>
      <p className="mb-4 text-sm text-white/60">
        How much ground do you want to cover between attractions? This changes how much walking time we budget
        into your schedule.
      </p>
      <div className="flex flex-col gap-3">
        {WALKING_PACE_OPTIONS.map((opt) => (
          <ChoiceCard
            key={opt.value}
            selected={preferences.walking_pace === opt.value}
            onClick={() => setPreferences((p) => ({ ...p, walking_pace: opt.value }))}
            title={opt.label}
            body={opt.body}
          />
        ))}
      </div>
    </div>
  );
}

function ArrivalDepartureStep({
  preferences,
  setPreferences,
}: {
  preferences: Preferences;
  setPreferences: React.Dispatch<React.SetStateAction<Preferences>>;
}) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-semibold text-white">When are you at the park?</p>
      <p className="text-sm text-white/60">Leave either blank to use official park hours.</p>
      <div className="mt-2 flex items-center gap-2 text-sm">
        <input
          type="time"
          value={timeFromIso(preferences.planned_arrival)}
          onChange={(e) =>
            setPreferences((p) => ({ ...p, planned_arrival: e.target.value ? combineTodayWithTime(e.target.value) : null }))
          }
          className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white"
        />
        <span className="text-white/40">to</span>
        <input
          type="time"
          value={timeFromIso(preferences.planned_departure)}
          onChange={(e) =>
            setPreferences((p) => ({ ...p, planned_departure: e.target.value ? combineTodayWithTime(e.target.value) : null }))
          }
          className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white"
        />
      </div>
    </div>
  );
}
