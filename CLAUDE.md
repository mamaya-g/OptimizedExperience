# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

A Disneyland single-day itinerary optimizer -- a preference- and live-data-driven "day
co-pilot," not a clone of Disney's own app. Full design rationale (API comparisons,
algorithm choice, AI Council review) lives in
`/Users/decipherer/.claude/plans/graceful-watching-toast.md`; day-to-day usage lives in
`README.md`.

**Phase 1 + Plan 2 + Plan 3 (current):** full stack, live end to end -- Python backend
(two solvers behind one `Solver` contract, CLI, FastAPI HTTP API) and a Next.js
itinerary-viewer frontend, deployable to Render (backend) + Vercel (frontend) via
`render.yaml` at the repo root. Plan 2 added: an optional Lightning Lane toggle,
mandatory meal/shopping blocks, a guest entry/exit window, real walking time under three
navigation strategies (time-optimal / land-order / clustered), and hourly wait-time
forecasting. Plan 3 added the OR-Tools routing solver and the API/frontend. Indoor/outdoor
queue scoring is explicitly deferred (no reliable public data source) -- see README.md.
Frontend v1 is viewer-only by design (objective/solver toggles only) -- all other guest
settings stay file-based via `preferences.yaml`; don't add in-browser editing without
being asked, that's an intentional, discussed scope boundary, not an oversight.

## Commands

All commands run from `backend/`. The project targets Python >=3.11 (uses `X | None`
union syntax) -- the system Python may be older; if so, install a newer one via
`brew install python@3.12` and create the venv with that interpreter.

```bash
.venv/bin/pip install -e ".[dev]"          # install deps (editable install)
.venv/bin/python -m pytest                 # run all tests (~45s -- OR-Tools tests solve for real)
.venv/bin/python -m pytest tests/test_greedy.py::test_prefers_higher_prize_per_minute  # single test

# Generate a plan (offline, no network -- use this for iteration/demos):
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli \
  --replay tests/fixtures/disneyland_aug16 --mode maximize_prize

# Compare the greedy vs. OR-Tools solver on the same day:
PYTHONPATH=src .venv/bin/python scripts/compare_solvers.py

# Run the HTTP API locally (frontend/ expects it on :8000 by default):
PYTHONPATH=src .venv/bin/uvicorn optimized_experience.api.main:app --reload
```

Frontend (from `frontend/`): `npm install && npm run dev`. Needs the API running (see
above) and `NEXT_PUBLIC_API_BASE` set (`.env.example` has the local default).

Editable installs (`pip install -e`) may not add the package to `sys.path` in every
environment (observed in this sandbox: `.pth` files in `site-packages` are silently not
processed at interpreter startup, even though they're written correctly and `pip show`
reports the install as successful). If `import optimized_experience` fails, prefix
commands with `PYTHONPATH=src` as shown above -- pytest already does this via
`pythonpath = ["src"]` in `pyproject.toml`, so plain `pytest` works without the prefix.

## Architecture

- `backend/src/optimized_experience/data/` -- external data access: `client.py`
  (themeparks.wiki, real + fixture-replay implementations behind a `DataSource`
  Protocol), `weather_client.py` (api.weather.gov, same real/replay split),
  `preferences.py` (guest tiers + all Plan-2 day-level settings: Lightning Lane
  toggle, walking pace, navigation strategy, arrival/departure, activity blocks),
  `reliability.py` and `lands.py` (both hand-authored YAML config loaders, same
  pattern: qualitative data no API exposes, refinable over time).
- `backend/src/optimized_experience/optimizer/` -- the solver layer, all built against
  one shared contract (`contracts.py`: `Node`, `PlanRequest`, `Plan`, `Solver` Protocol,
  `Coordinates` with a haversine `distance_miles()`) so solvers are interchangeable via
  `factory.py`'s `get_solver(objective, solver_name)`. Three solvers today: `greedy.py`
  and `greedy_challenge.py` (`MAXIMIZE_PRIZE` and `ALL_RIDES_CHALLENGE` objectives,
  respectively -- both thread a `_NavState` of current location/land, and under
  `LAND_ORDER` the land the solver is currently restricted to, through their solve
  loop), and `ortools_solver.py` (`ORToolsSolver`, handles *both* objectives in one
  class since they only differ in penalty weighting there -- a genuine prize-collecting
  VRPTW global search via OR-Tools' routing library, not a heuristic; read its module
  docstring before touching it, it documents two real bugs found and fixed during
  development -- an LL-vs-standby option picked upfront instead of left to the solver,
  and a transit-cost formula that charged the wrong node's service time -- plus the
  simplifications it still makes on purpose to stay tractable). `lightning_lane.py` and
  `navigation.py` hold logic shared by the two greedy solvers (LL capacity-1 resource
  state machine; land-order eligibility + clustered land-switch penalty). `geography.py`
  has the walking-pace-to-minutes conversion, used by all three solvers. `scoring.py`
  computes `effective_prize()`, the single mechanism behind both ride-breakdown-risk and
  water-ride weather-comfort adjustments (an hour-dependent multiplier on a node's base
  prize) -- `Node.wait_minutes_at()` is the analogous mechanism for hourly wait-time
  forecasting.
- `backend/src/optimized_experience/api/main.py` -- FastAPI app for the frontend:
  `GET /health`, `GET /api/plan?objective=...&solver=...`. Reuses `cli.generate_plan()`/
  `build_sources()` directly rather than duplicating orchestration; always live (no
  replay mode) since this is the "real app" surface, not a test/demo entrypoint. Data
  sources are built once at import time and reused for the process lifetime so the
  existing TTL caching actually helps across requests -- don't rebuild them per request.
- `backend/src/optimized_experience/planning.py` -- bridges the data layer into the
  optimizer contract (raw API responses + preferences + reliability profile + land map
  -> candidate `Node`s -> `PlanRequest`). Kept separate from `cli.py` so this
  orchestration is testable without going through argument parsing. Meal/shopping
  blocks (`build_activity_nodes()`) are modeled as mandatory `ACTIVITY`-kind `Node`s
  reusing the exact scheduling path shows already use (narrow feasibility window + a
  forcing prize constant), not a parallel subsystem -- see `MANDATORY_ACTIVITY_PRIZE`
  and `_SOLVER_CHOICE_DEFAULT_WINDOW` (the latter exists because a mandatory block's
  forcing prize would otherwise get grabbed at park open just because that's the first
  opportunity, which is wrong for something named "Dinner").
- `backend/src/optimized_experience/cli.py` -- entrypoint; owns argument parsing, the
  `--watch` rolling re-plan loop (full recompute per tick, not incremental patching --
  reloads `preferences.yaml`/`reliability_profile.yaml` every tick so mid-day edits take
  effect without restarting), `--navigation compare`, `--solver
  {greedy,ortools,compare}`, and printing. `scripts/demo_plan.py`,
  `scripts/compare_solvers.py`, and `api/main.py` all import `generate_plan()`/
  `build_sources()` from here rather than duplicating orchestration logic.
- `frontend/app/` -- Next.js App Router itinerary viewer: `page.tsx` (client component,
  fetches `/api/plan` on mount and on objective/solver select change via
  `useTransition` -- not raw `useState` loading flags, the lint config here flags
  synchronous `setState` in effects), `lib/types.ts` (mirrors the backend's
  `Plan`/`PlanStep` shapes), `lib/api.ts` (`fetchPlan()`), `components/ItineraryCard.tsx`
  (action-colored card, one per `PlanStep`). Deliberately viewer-only -- see "Project
  status" above before adding editing features.
- Tests are offline and deterministic: `tests/fixtures/disneyland_aug16/` holds real
  recorded API responses (children/live/schedule/weather) for `ReplayDataSource` /
  `ReplayWeatherSource` to serve, so nothing requires a live park visit or network
  access to test or demo.

## Git workflow (required)

This repository is the durable record of the project's progress. Commit and push regularly so no work is ever at risk of being lost, and so changes can be reverted easily.

- Commit early and often: after completing any coherent unit of work (a feature, a fix, a file scaffold), stage and commit it rather than letting changes pile up uncommitted.
- Write clean, descriptive commit messages: a concise summary line (why, not just what), with a body if the change needs more explanation. Follow the existing commit message style once one is established.
- Push to GitHub (`origin`) after committing, so `origin/main` stays close to local `main` and always has a recent, working save point.
- Only create commits/pushes for real, intentional units of work — do not commit broken or half-finished code without noting that in the message.
- Never use destructive git operations (`push --force`, `reset --hard`, amending pushed commits, etc.) without explicit confirmation first.
