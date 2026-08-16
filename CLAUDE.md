# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This project is brand new and does not yet have an established architecture, build system, or test suite. This section (and the rest of this file) should be filled in with real commands and architecture notes as soon as they exist — do not leave placeholder/generic content here once the codebase has structure.

## Git workflow (required)

This repository is the durable record of the project's progress. Commit and push regularly so no work is ever at risk of being lost, and so changes can be reverted easily.

- Commit early and often: after completing any coherent unit of work (a feature, a fix, a file scaffold), stage and commit it rather than letting changes pile up uncommitted.
- Write clean, descriptive commit messages: a concise summary line (why, not just what), with a body if the change needs more explanation. Follow the existing commit message style once one is established.
- Push to GitHub (`origin`) after committing, so `origin/main` stays close to local `main` and always has a recent, working save point.
- Only create commits/pushes for real, intentional units of work — do not commit broken or half-finished code without noting that in the message.
- Never use destructive git operations (`push --force`, `reset --hard`, amending pushed commits, etc.) without explicit confirmation first.
