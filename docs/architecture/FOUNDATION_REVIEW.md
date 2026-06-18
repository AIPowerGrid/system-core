# Foundation Review — the new grid (`grid_api`)

Critical review done before scaling to a public utility with real money. Evidence
is from the codebase as of this review; line counts are approximate.

## Summary verdict

`grid_api` is a **solid working service, not yet a public-utility foundation.** The
core is healthier than the repo size implies, but a handful of form cracks and one
function-level hole (safety) must be closed in the one cheap window we have now.

**Do not rewrite.** The decoupling, modularity, and tested money-paths are real
assets a rewrite would throw away (and re-introduce already-fixed bugs). Subtract
and consolidate, then extend.

## Repo shape

- `horde/` — ~25.3K LOC legacy Flask AI-Horde fork, **being decommissioned** (#44).
  72% of the repo. `grid_api` is already decoupled from it (only ~10 string refs,
  all *deliberate avoidance* — e.g. `auth.py` reimplements `hash_api_key` to avoid
  importing `horde.utils`; `database.py` "only ever touch tables we own"). Clean
  amputation is feasible.
- `grid_api/` — ~9.6K LOC, the live v2 (FastAPI, OpenAI/Anthropic `/v1`, worker WS).
  This is "the grid." Everything below is about it.

## What's genuinely good (keep these)

- Clean `routers/` + `services/` separation; decoupled from the horde.
- On-chain reads are **off the hot path** (ModelVault sync on a 600s loop) — the
  caching lesson is already learned; apply the same to RecipeVault.
- **The money paths are the ones with tests**: `job_queue`, `den`, `quota`,
  settlement `merkle`/`ipfs`. Right instinct on where correctness matters most.
- Real token streaming (not poll), faithful OpenAI/Anthropic passthrough.
- The on-chain economic spine (credits/den/ledger/settlement/bonding) — the moat.

## Foundation cracks (ranked by how fast they rot)

1. **No central config.** ~46 `getenv`/`environ` reads across 14 files, untyped,
   unvalidated, no single source of truth. The #1 rot vector in every service.
   **Fix:** one typed `Settings` (pydantic-settings), validated + fail-fast on boot,
   zero `getenv` outside it.
2. **Test coverage thin and lopsided.** ~736 test LOC / 9.6K (~7.7%), 5 files, all
   economic. **Zero tests** on API routers (`openai`/`images`/`videos`/`anthropic`),
   `auth.py`, and `worker_ws.py` — the last being the 1,111-LOC god-file where the
   nastiest bugs lived (eviction cascade, idle-redelivery). Highest-risk code is the
   least tested. **Fix:** contract tests per router + auth + dispatch.
3. **Error discipline.** ~47 broad `except Exception` + **6 bare `except:`** (these
   swallow `KeyboardInterrupt`/`SystemExit` and hide bugs). **Fix:** ban bare
   excepts; one structured error envelope; a small error taxonomy.
4. **God-file.** `worker_ws.py` (1,111 LOC) does registration + dispatch + health +
   eviction + streaming. **Fix:** split into `registration / dispatch / health /
   stream`.
5. **Dead scaffolding in the main line.** Five job-queue modules; only Redis
   `services/job_queue.py` is wired. `services/p2p/*`, `waku_queue.py`,
   `*_hybrid.py` (~1.5K LOC) are **default-off** (`P2P_ENABLED=false`). **Fix:**
   branch them out (ADR-0001); they're decision-debt sitting in the trunk.

## Function-level hole: safety (blocking for public)

`services/sanitizer.py` is a **secrets redactor** (strips API keys/PGP blocks from
prompts), **not** a content filter. There is **no CSAM/NSFW prompt filtering and no
IP-abuse controls** — the legacy horde had `detection.py` + `countermeasures.py`
for exactly this. For a public utility this is a missing *license to operate*, not a
missing feature. See [SAFETY_MODEL.md](SAFETY_MODEL.md).

## The 7 properties a public-utility foundation needs

Score honestly; features are the easy part.

| # | Property | Why it's foundational | Status |
|---|---|---|---|
| 1 | **Verifiability** | the moat: graph integrity + slashing + validators + TEE | designed, partially built |
| 2 | **Safety / legal** | CSAM, moderation, takedown, jurisdiction = license to operate | **❌ absent — blocking** |
| 3 | **Money integrity** | ungameable metering, settlement correctness, idempotency, pre-money audit (#46) | partial; audit pending |
| 4 | **Resilience** | coordinator is a SPOF (Redis-centered) today — acceptable, but keep it *swappable to HA* | acceptable, watch |
| 5 | **Governance** | who approves recipes/models, upgrades the diamond, sets policy (multisig→DAO?) | roles exist, model undefined |
| 6 | **Protocol openness** | a *utility* needs a published worker/recipe/settlement spec + SDK others can implement | not yet — makes it a public good vs a company |
| 7 | **Privacy** | prompts are user data; tee observes them — need a stance → TEE endgame | roadmapped |

## Hardening sprint (concrete, ~1–2 weeks, no features)

- [ ] `grid_api/config.py` — typed `Settings`, validated on boot; migrate all 46
      env reads; CI check that forbids `getenv` outside it.
- [ ] Structured error envelope + taxonomy; remove 6 bare excepts; audit the 47
      broad excepts (narrow or justify each).
- [ ] Split `worker_ws.py` into 4 modules; add dispatch + registration tests.
- [ ] Router/auth contract tests (`openai`, `images`, `videos`, `anthropic`,
      `accounts`, `auth`).
- [ ] Branch out `services/p2p`, `waku_queue`, `*_hybrid` (ADR-0001).
- [ ] Finish horde amputation (#44): own tables verified, `horde/` deleted.

These are debt paydown; do them before the recipe layer so it lands on clean ground.
