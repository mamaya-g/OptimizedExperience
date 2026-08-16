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

**Phase 1 (current):** Python backend -- live data + greedy solver + CLI.
Runnable and testable end-to-end without a live park visit. No UI yet.

Phase 2 (OR-Tools solver) and Phase 3 (Next.js UI) are not started.

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
  is planned for phase 2, behind the same `Solver` contract.

## Running it (backend)

```bash
cd backend
python3.12 -m venv .venv   # project targets Python >=3.11 (uses `X | None` unions)
.venv/bin/pip install -e ".[dev]"

# Copy the example config and edit for your own visit:
cp config/preferences.example.yaml config/preferences.yaml
cp config/reliability_profile.example.yaml config/reliability_profile.yaml
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

# Keep re-planning every ~2 minutes as live data changes:
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli --watch
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
    data/         # themeparks.wiki + NWS weather clients, preferences, reliability
    optimizer/    # PlanRequest/Plan contract, greedy solvers, scoring
    planning.py   # bridges data layer -> optimizer contract
    cli.py        # entrypoint
  tests/          # unit tests + recorded fixtures (offline, deterministic)
  scripts/        # demo_plan.py, collect_status_log.py
  config/         # preferences.example.yaml, reliability_profile.example.yaml
```
