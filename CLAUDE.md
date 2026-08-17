# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

A Disneyland single-day itinerary optimizer -- a preference- and live-data-driven "day
co-pilot," not a clone of Disney's own app. Full design rationale (API comparisons,
algorithm choice, AI Council review) lives in
`/Users/decipherer/.claude/plans/graceful-watching-toast.md`; day-to-day usage lives in
`README.md`.

**Phase 1 + Plan 2 (current):** Python backend only -- live data + greedy solvers + CLI.
No UI yet. Plan 2 added: an optional Lightning Lane toggle, mandatory meal/shopping
blocks, a guest entry/exit window, real walking time under three navigation strategies
(time-optimal / land-order / clustered), and hourly wait-time forecasting. An OR-Tools
solver and a Next.js UI are not started -- re-plan those in detail only once the prior
work is solid; don't jump ahead. Indoor/outdoor queue scoring is explicitly deferred (no
reliable public data source) -- see README.md.

## Commands

All commands run from `backend/`. The project targets Python >=3.11 (uses `X | None`
union syntax) -- the system Python may be older; if so, install a newer one via
`brew install python@3.12` and create the venv with that interpreter.

```bash
.venv/bin/pip install -e ".[dev]"          # install deps (editable install)
.venv/bin/python -m pytest                 # run all tests
.venv/bin/python -m pytest tests/test_greedy.py::test_prefers_higher_prize_per_minute  # single test

# Generate a plan (offline, no network -- use this for iteration/demos):
PYTHONPATH=src .venv/bin/python -m optimized_experience.cli \
  --replay tests/fixtures/disneyland_aug16 --mode maximize_prize
```

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
  `factory.py`'s `get_solver()`. `greedy.py` and `greedy_challenge.py` are today's two
  solvers (`MAXIMIZE_PRIZE` and `ALL_RIDES_CHALLENGE` objectives, respectively); both
  thread a `_NavState` (current location/land, and under `LAND_ORDER` the land the
  solver is currently restricted to) through their solve loop. `lightning_lane.py` and
  `navigation.py` hold logic shared by both solvers (LL capacity-1 resource state
  machine; land-order eligibility + clustered land-switch penalty) so it isn't
  duplicated per solver. `geography.py` has the walking-pace-to-minutes conversion.
  `scoring.py` computes `effective_prize()`, the single mechanism behind both
  ride-breakdown-risk and water-ride weather-comfort adjustments (an hour-dependent
  multiplier on a node's base prize) -- `Node.wait_minutes_at()` is the analogous
  mechanism for hourly wait-time forecasting.
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
  effect without restarting), `--navigation compare` (solves the same day under all
  three navigation strategies and prints all three), and printing. `scripts/demo_plan.py`
  and `scripts/collect_status_log.py` both import from here rather than duplicating
  orchestration logic.
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
