# DOX framework

- DOX is a hierarchy of AGENTS.md files that carry the durable contracts for this repo.
- Agents must follow the DOX chain on every edit.

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees.
- Any work product must stay understandable from the nearest AGENTS.md plus every parent above it.

## Read Before Editing

1. Read this root AGENTS.md.
2. Identify every path you expect to touch.
3. Walk from repo root to each target, reading every AGENTS.md on the way.
4. The nearest AGENTS.md is the local contract; parents hold repo-wide rules.
5. If docs conflict, the closer doc controls local detail, but no child may weaken DOX.

Do not rely on memory — re-read the applicable chain in-session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done. Update the closest
owning AGENTS.md when a change affects: purpose/scope/ownership; durable structure,
contracts, or workflows; inputs/outputs/permissions/side-effects; or the Child DOX Index.
Remove stale text immediately. Refresh affected parent and child indexes.

## Style

Concise, current, operational. Stable contracts, not diary entries. Broad rules in parents,
concrete detail in children. Delete stale notes instead of explaining history.

---

# system-core — the AI Power Grid coordinator

## Purpose

The grid's coordination service. Exposes OpenAI/Anthropic-compatible `/v1` endpoints,
dispatches text/image/video jobs to GPU workers over WebSocket, meters usage, and settles
rewards on-chain (Base). This is "the new grid."

## Ownership

- **`grid_api/`** — the live v2 service (FastAPI). **All new work lands here.** Owned in
  its own AGENTS.md.
- **`horde/`** — LEGACY Flask AI-Horde fork, being decommissioned (#44). Do **not** build
  new features here. `grid_api` is already decoupled from it (shares only the Postgres
  instance, different tables). No DOX child — it is scheduled for deletion.
- **`alembic/`** — DB migrations for grid_api-owned tables.
- **`docs/architecture/`** — foundation review, parity matrix, safety model, ADR log.
  Read these before architectural changes; they are the source of truth for *form*.

## Local Contracts

- **Inherit org engineering standards:** `aipg-documentation/engineering-standards/`
  (core + `git.md` + `python.md`). The rules below are system-core specializations.
- **The spine (ADR-0001):** centralized coordinator + decentralized *verifiable* compute +
  on-chain economics. Trust comes from verification + stake, not from removing the
  coordinator. P2P/mesh coordination is a deferred research track — not the main line.
- On-chain reads happen on background sync loops (`main.py`), never on the request hot path.
- Secrets never reach workers in the clear; jobs upload results via grid-issued presigned
  R2 URLs (never standing bucket creds on a worker).
- Safety is defense-in-depth with a mandatory centralized CSAM backstop (ADR-0002) — see
  `docs/architecture/SAFETY_MODEL.md`.

## Work Guidance

- New env vars: add to the (planned) typed `grid_api/config.py`, not ad-hoc `getenv`.
- No bare `except:`. Errors return the structured envelope.
- Before scaling: see `docs/architecture/FOUNDATION_REVIEW.md` hardening sprint.

## Verification

- `pytest` (tests live under `grid_api/services/*/tests/` and `grid_api/services/tests/`).
- `alembic upgrade head` must apply cleanly on a fresh DB.

## Child DOX Index

- [grid_api/AGENTS.md](grid_api/AGENTS.md) — the live v2 coordinator service.
- `docs/architecture/README.md` — architecture decisions + foundation docs (not an AGENTS.md, but read it).
