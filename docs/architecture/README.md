# Grid Architecture — Foundation Docs

These docs capture the architectural review of the **new grid** (`grid_api`) done
before going "big" (public, real money), and the decisions that should keep it in
good shape as it grows. They are the source of truth for *form and function* —
refactor the code against these, not the other way around.

| Doc | What it is |
|---|---|
| [FOUNDATION_REVIEW.md](FOUNDATION_REVIEW.md) | Critical review of `grid_api`: how it turned out, the cracks to fix before scaling, and the 7 properties a public-utility foundation needs. |
| [PARITY_MATRIX.md](PARITY_MATRIX.md) | Legacy AI-Horde vs new grid — what we kept, replaced, dropped on purpose, and the real gaps. |
| [SAFETY_MODEL.md](SAFETY_MODEL.md) | Content-safety architecture: centralized now → decentralized (validator) future. Answers "do we give safety to validator nodes?" |

## The spine (ADR-0001 — decided)

> **The grid is a centralized coordinator + decentralized, *verifiable* compute +
> on-chain economics.**

Trustlessness comes from **verification and money at stake** (RecipeVault graph
integrity, bonding/slashing, validators, eventual TEE) — **not** from removing the
coordinator. A P2P/mesh coordinator is explicitly a *future research track*, not
the main line. Everything below follows from this.

## Decision log (ADR-lite)

- **ADR-0001 — Spine.** Centralized coordinator, verifiable decentralized compute,
  on-chain economics. P2P coordinator deferred to research. → delete/branch
  `services/p2p`, `waku_queue`, `*_hybrid` from the main line.
- **ADR-0002 — Safety is defense-in-depth, not delegated.** Content safety is NOT
  treated like compute correctness. Deterministic filter + classifier + a
  **mandatory centralized CSAM backstop** at the coordinator stay even after
  validators do decentralized re-screening. Legal liability cannot be outsourced.
  See [SAFETY_MODEL.md](SAFETY_MODEL.md).
- **ADR-0003 — The graph layer lives at the grid, backed by RecipeVault.** Clients
  reference an on-chain approved recipe + typed inputs, never a raw graph. Workers
  become dumb executors. Retires grid-comfy-bridge `model_mapper`.
- **ADR-0004 — Drop horde-isms on purpose.** Kudos→on-chain credits, styles→recipes,
  gen-params→workflow, teams/news removed. See [PARITY_MATRIX.md](PARITY_MATRIX.md).

## What to do before going big (sequenced)

1. **Lock the spine** (ADR-0001). One sentence, done above.
2. **Foundation hardening sprint** (pure debt, no features): central typed config,
   structured error envelope, delete p2p scaffolding, split `worker_ws.py`, test
   the routers + `auth` + dispatch. See FOUNDATION_REVIEW §"Cracks".
3. **Safety layer** — content + IP/abuse. *Blocking gate for public.* See SAFETY_MODEL.
4. **Recipe/graph layer** + trust loop (validators / slashing / metering).
5. **Keep writing it down** — new ADRs here for every load-bearing decision.

## Conventions

- One ADR per load-bearing decision, appended to the log above. An ADR is a
  decision that's expensive to reverse; if it's cheap to reverse, it's not an ADR.
- A decision that isn't written here doesn't exist. That's the anti-rot rule.
