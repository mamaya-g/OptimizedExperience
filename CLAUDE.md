# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

A Disneyland single-day itinerary optimizer -- a preference- and live-data-driven "day
co-pilot," not a clone of Disney's own app. Full design rationale (API comparisons,
algorithm choice, AI Council review) lives in
`/Users/decipherer/.claude/plans/graceful-watching-toast.md`; day-to-day usage lives in
`README.md`.

**Phase 1 (current):** Python backend only -- live data + greedy solver + CLI. No UI yet.
Phase 2 (OR-Tools solver) and Phase 3 (Next.js UI) are not started -- re-plan those in
detail only once the prior phase is working; don't jump ahead.

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
  `preferences.py` and `reliability.py` (hand-authored YAML config loaders).
- `backend/src/optimized_experience/optimizer/` -- the solver layer, all built against
  one shared contract (`contracts.py`: `Node`, `PlanRequest`, `Plan`, `Solver` Protocol)
  so solvers are interchangeable via `factory.py`'s `get_solver()`. `greedy.py` and
  `greedy_challenge.py` are today's two solvers (`MAXIMIZE_PRIZE` and
  `ALL_RIDES_CHALLENGE` objectives, respectively); `lightning_lane.py` holds the
  Lightning Lane Multi Pass capacity-1 resource state machine shared by both, so it
  isn't duplicated per solver. `scoring.py` computes `effective_prize()`, the single
  mechanism behind both ride-breakdown-risk and water-ride weather-comfort adjustments
  (an hour-dependent multiplier on a node's base prize).
- `backend/src/optimized_experience/planning.py` -- bridges the data layer into the
  optimizer contract (raw API responses + preferences + reliability profile ->
  candidate `Node`s -> `PlanRequest`). Kept separate from `cli.py` so this orchestration
  is testable without going through argument parsing.
- `backend/src/optimized_experience/cli.py` -- entrypoint; owns argument parsing, the
  `--watch` rolling re-plan loop (full recompute per tick, not incremental patching),
  and printing. `scripts/demo_plan.py` and `scripts/collect_status_log.py` both import
  from here rather than duplicating orchestration logic.
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
