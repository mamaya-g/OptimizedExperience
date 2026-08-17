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

**Phase 1 + Plan 2 + Plan 3 (current):** the full stack is live -- Python
backend (two solvers, CLI, HTTP API) and a Next.js itinerary viewer, both
running against real Disneyland/weather data end to end.

- Phase 1: greedy solvers (`MAXIMIZE_PRIZE` / `ALL_RIDES_CHALLENGE`) + CLI.
- Plan 2: realism the phase-1 greedy oversimplified -- an optional Lightning
  Lane toggle, mandatory meal/shopping blocks, a guest-specified entry/exit
  window, real walking time between attractions under three navigation
  strategies, and hourly wait-time forecasting.
- Plan 3: an OR-Tools routing solver (a genuine global search, not a
  heuristic) behind the same `Solver` contract, plus a FastAPI backend and a
  Next.js itinerary-viewer frontend, deployable to Render + Vercel.

See `/Users/decipherer/.claude/plans/graceful-watching-toast.md` for the full
design rationale of each round.

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
- **Solvers:** a naive greedy heuristic (fast, myopic, phase 1) and an
  OR-Tools routing solver (`optimizer/ortools_solver.py`) -- a genuine
  prize-collecting VRPTW global search over real travel time, not a
  step-by-step heuristic. Both implement the same `Solver` contract, selected
  via `optimizer/factory.py`'s `get_solver()`. Run
  `scripts/compare_solvers.py` to see total prize + solve time for both side
  by side on the same day; OR-Tools should score at least as well, being a
  genuine search rather than a myopic pass, though it makes its own
  documented simplifications (see that module's docstring) to stay
  tractable.
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

# Use the OR-Tools solver instead of the greedy, or compare both:
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli --solver ortools
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli --solver compare
```

### Demo both modes at once

```bash
PYTHONPATH=src .venv/bin/python scripts/demo_plan.py
```

### Compare the greedy vs. OR-Tools solver

```bash
PYTHONPATH=src .venv/bin/python scripts/compare_solvers.py
```

### Run the HTTP API locally

```bash
PYTHONPATH=src .venv/bin/uvicorn optimized_experience.api.main:app --reload
# GET http://localhost:8000/api/plan?objective=maximize_prize&solver=greedy
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

## Running it (frontend)

An itinerary-viewer-only Next.js app (v1 scope -- see the plan notes: no
in-browser editing of tiers/activities/etc., that stays file-based via
`preferences.yaml`; just view a live-solved plan and toggle objective/solver).

```bash
cd frontend
npm install
cp .env.example .env.local   # points at the local backend by default
npm run dev
# open http://localhost:3000 (make sure the backend is running too, see above)
```

## Deployment

Backend on Render, frontend on Vercel. Both are configured in this repo, but
going live needs your own accounts connected -- I can't do that step for you.

**Backend (Render):**
1. Push this repo to GitHub (already done if you're reading this from there).
2. In the Render dashboard: New -> Blueprint -> connect this repo. It reads
   `render.yaml` at the repo root automatically (Python service rooted at
   `backend/`, installs deps, seeds config from the `.example.yaml` files,
   runs uvicorn).
3. Note the resulting service URL (e.g. `https://optimized-experience-api.onrender.com`).
4. Once you know the frontend's Vercel URL (next step), come back and set
   the `CORS_ALLOWED_ORIGINS` env var on the Render service to that URL, or
   the browser will block the frontend's requests.

**Frontend (Vercel):**
1. In the Vercel dashboard: Add New -> Project -> import this repo.
2. Set **Root Directory** to `frontend` (Next.js is auto-detected from there,
   no other config needed).
3. Add an environment variable: `NEXT_PUBLIC_API_BASE` = your Render backend
   URL from above.
4. Deploy. Then go back and set Render's `CORS_ALLOWED_ORIGINS` to this
   Vercel URL (step 4 above) and redeploy the backend.

## Repo layout

```
backend/
  src/optimized_experience/
    data/         # themeparks.wiki + NWS weather clients, preferences, reliability, lands
    optimizer/    # PlanRequest/Plan contract, solvers (greedy + OR-Tools), scoring, geography, navigation
    api/          # FastAPI app (main.py) -- the HTTP surface for the frontend
    planning.py   # bridges data layer -> optimizer contract
    cli.py        # entrypoint
  tests/          # unit tests + recorded fixtures (offline, deterministic)
  scripts/        # demo_plan.py, compare_solvers.py, collect_status_log.py
  config/         # preferences.example.yaml, reliability_profile.example.yaml, land_map.example.yaml
frontend/
  app/            # Next.js App Router -- itinerary viewer (page.tsx, components/, lib/)
render.yaml       # Render deploy config for the backend (repo root, per Render's convention)
```
