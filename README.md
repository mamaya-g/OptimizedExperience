# Optimized Experience

A Disneyland single-day itinerary optimizer -- a "day co-pilot" that turns your
attraction preferences (must-go / nice-to-have / skip) plus live park data
into a full-day recommended schedule, then keeps it fresh as conditions
change through the day.

Unlike Disney's own app (which is reactive -- current wait times, book-the-next-Lightning-Lane),
this is anticipatory: it generates a plan up front, factors in things Disney's
app doesn't reason about at all (which attractions historically go down and
when, live/forecast weather for water-ride comfort), and offers an "All Rides
Challenge" mode for guests trying to ride everything in one day.

See `/Users/decipherer/.claude/plans/graceful-watching-toast.md` for the full
design rationale (API comparisons, algorithm choice, AI Council review).

## Status

**Phase 1 + Plan 2 (current):** Python backend -- live data + greedy solvers + CLI.
Runnable and testable end-to-end without a live park visit. No UI yet.

Plan 2 added realism the phase-1 greedy oversimplified: an optional Lightning
Lane toggle, mandatory meal/shopping blocks, a guest-specified entry/exit
window, real walking time between attractions (from actual coordinates) under
three navigation strategies, and hourly wait-time forecasting instead of a
flat current-snapshot estimate. See
`/Users/decipherer/.claude/plans/graceful-watching-toast.md` for the full
design rationale.

An OR-Tools CP-SAT solver and a Next.js UI are not started yet.

**Deferred:** indoor/outdoor/shaded queue status per attraction -- no
reliable public data source covers all ~50 attractions (only scattered blog
mentions of a handful of "notable" queues). When better data exists, this
would plug into the exact same hour-dependent multiplier pattern
`scoring.py` already uses for weather-comfort (`weather_comfort_factor()`),
alongside a new `indoor_outdoor_factor()`.

## How it works

- **Live park data:** [themeparks.wiki](https://api.themeparks.wiki/v1) --
  free, no auth, sourced directly from Disney's own systems, ~2min refresh.
- **Weather data:** [api.weather.gov](https://api.weather.gov) (US National
  Weather Service) -- free, no auth, used for water-ride comfort scoring.
- **Algorithm:** the Tourist Trip Design Problem, modeled as an Orienteering
  Problem with Time Windows (maximize preference-weighted "prize" within a
  time budget). Breakdown-risk and weather-comfort are both modeled as the
  same hour-dependent multiplier on a node's prize (an Orienteering Problem
  with Stochastic Profits, approximated via expected-value discounting).
  Lightning Lane Multi Pass is modeled as a capacity-1 resource -- only one
  booked hold at a time, which is the actual "Waze" analogue in this project
  (continuous recalculation of when to book/redeem), more than pathfinding is.
- **Solver:** a naive greedy heuristic (phase 1). An OR-Tools CP-SAT solver
  is planned for a future round, behind the same `Solver` contract.
- **Real walking time:** haversine distance between attractions' actual
  coordinates, divided by a guest-selected walking pace (slow/average/fast).
  No official "land" grouping exists in any API, so land-to-attraction
  mapping is hand-seeded (`config/land_map.example.yaml`), same pattern as
  the reliability tiers. Three navigation strategies -- time-optimal, a
  guest-specified land order, or a soft same-land clustering preference --
  can all be solved and compared side by side (`--navigation compare`).
- **Meal/shopping blocks:** mandatory `ACTIVITY` nodes that reuse the exact
  scheduling machinery attractions/shows already use (a narrow feasibility
  window + a forcing prize constant), not a parallel subsystem. Each block
  picks one of three placement styles: a preferred time range, an exact
  fixed time, or "solver chooses" (with a sensible default hour-of-day window
  per meal kind, not "any time" -- see `planning._SOLVER_CHOICE_DEFAULT_WINDOW`).

## Running it (backend)

```bash
cd backend
python3.12 -m venv .venv   # project targets Python >=3.11 (uses `X | None` unions)
.venv/bin/pip install -e ".[dev]"

# Copy the example config and edit for your own visit:
cp config/preferences.example.yaml config/preferences.yaml
cp config/reliability_profile.example.yaml config/reliability_profile.yaml
cp config/land_map.example.yaml config/land_map.yaml
```

> Note: editable installs (`pip install -e`) may not add the package to
> `sys.path` in every environment. If `import optimized_experience` fails,
> run everything with `PYTHONPATH=src` prefixed, as shown below.

### Generate a plan

```bash
# Offline, using recorded fixture data (no network needed):
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli \
  --replay tests/fixtures/disneyland_aug16 --mode maximize_prize

PYTHONPATH=src .venv/bin/python -m optimized_experience.cli \
  --replay tests/fixtures/disneyland_aug16 --mode all_rides_challenge

# Live, against the real APIs (only meaningful while Disneyland is open):
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli --mode maximize_prize

# Keep re-planning every ~2 minutes as live data changes. --watch also reloads
# preferences.yaml/reliability_profile.yaml each tick, so editing them
# mid-day (e.g. turning off Lightning Lane) takes effect without restarting:
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli --watch

# Solve the same day under all three navigation strategies and compare:
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli \
  --replay tests/fixtures/disneyland_aug16 --navigation compare
```

### Demo both modes at once

```bash
PYTHONPATH=src .venv/bin/python scripts/demo_plan.py
```

### Run the tests

```bash
.venv/bin/python -m pytest
```

### Collect real reliability history (optional, ongoing)

`reliability_profile.yaml` starts hand-seeded (no public API exposes
Disneyland-specific breakdown history). This script builds a real dataset
over time by logging live status snapshots -- run it periodically (e.g. via
cron):

```bash
PYTHONPATH=src .venv/bin/python scripts/collect_status_log.py
```

## Repo layout

```
backend/
  src/optimized_experience/
    data/         # themeparks.wiki + NWS weather clients, preferences, reliability, lands
    optimizer/    # PlanRequest/Plan contract, greedy solvers, scoring, geography, navigation
    planning.py   # bridges data layer -> optimizer contract
    cli.py        # entrypoint
  tests/          # unit tests + recorded fixtures (offline, deterministic)
  scripts/        # demo_plan.py, collect_status_log.py
  config/         # preferences.example.yaml, reliability_profile.example.yaml, land_map.example.yaml
```
