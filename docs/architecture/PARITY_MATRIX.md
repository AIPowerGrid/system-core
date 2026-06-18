# Feature Parity — legacy AI-Horde vs new grid

Goal: make sure the new grid covers the features **we care about**, and that what
we dropped was dropped *on purpose*. Legend:

- ✅ **covered** — present and at least as good
- 🔁 **replaced** — intentionally redesigned, the new way is better
- ⚠️ **partial** — exists but incomplete
- ❌ **gap** — missing and we care
- 🗑️ **dropped** — horde-ism we deliberately don't want

## Generation API

| Horde | New grid | Verdict |
|---|---|---|
| Text async/status/pop/submit (poll) | `/v1/chat/completions` streaming + worker WS | 🔁 better (real streaming) |
| Image async/status | `/v1/images` + media job queue | ✅ |
| Video (beta) | `/v1/videos` | ✅ |
| Interrogation (CLIP caption/tag) | — | ❌ minor; can be a recipe |
| Styles / collections | RecipeVault recipes | 🔁 superior (on-chain curated) |
| Gen params (loras, controlnet, post-proc, samplers) | encoded in the workflow/recipe | 🔁 cleaner — API shrinks |

## Worker lifecycle

| Horde | New grid | Verdict |
|---|---|---|
| Registration | worker WS register | ✅ |
| Heartbeat / health | WS health + strike/evict (#50) | ✅ |
| Per-worker maintenance / pause (operator control) | partial | ⚠️ add operator controls |
| Per-worker limits (max_power/threads/nsfw) | partial | ⚠️ |
| Trusted/flagged workers | on-chain bonding/slashing + WorkerRegistry | 🔁 better |
| Wallet address (EVM rewards) | core to the model | ✅ |
| Bridge agent version tracking | confirm | ⚠️ verify |
| Worker messages | — | ❌ low priority |
| Teams | — | 🗑️ |

## Job lifecycle

| Horde | New grid | Verdict |
|---|---|---|
| Async submit / status / cancel | `job_queue` | ✅ |
| Faulted / retry handling | requeue cap + stale reclaimer (#48/#49) | ✅ |
| R2 transient/permanent delivery (presigned) | `storage.py` | ✅ |
| Priority queue (kudos-based) | quota only, no QoS tiers | ⚠️ define priority model |

## Economy / incentives

| Horde | New grid | Verdict |
|---|---|---|
| Kudos (earn/spend/priority) | on-chain credits/den/settlement/ledger/pricing | 🔁 the upgrade |
| Monthly free kudos | free-tier daily quota (#35) | 🔁 done |
| Shared keys (multi-user tokens) | — | ❌ matters for studios/B2B |
| VPN/trusted/special/service/education roles | mostly dropped | ⚠️ keep service-acct + special-model gating |

## Accounts & auth

| Horde | New grid | Verdict |
|---|---|---|
| Registration + API keys (hashed) | `accounts.py` + `auth.py` | ✅ |
| Roles (mod/trusted/customizer/…) | narrower set | ⚠️ map the ones we need |
| OAuth (Google/Discord/GitHub) | — | ❌ nice-to-have |
| Suspicion / abuse scoring | `enforcement.py` (narrow) | ⚠️ thin |

## Anti-abuse / safety  ← the big parity gap

| Horde | New grid | Verdict |
|---|---|---|
| Prompt filters (regex, CSAM/NSFW) | `sanitizer.py` = **secrets only** | ❌ **critical, blocking** |
| NSFW output censoring | — | ❌ |
| IP timeouts / blocks / suspicion | — (only generic rate-limit) | ❌ |
| IP safety scoring (3rd-party) | — | ❌ lower priority |
| Raid / maintenance / invite-only modes | — | ⚠️ |

See [SAFETY_MODEL.md](SAFETY_MODEL.md) for the design.

## Stats & status

| Horde | New grid | Verdict |
|---|---|---|
| `/status/models` (availability + count/queue/eta) | `stats.py` + `/v1/models` | ✅ |
| totals / per-model / per-worker stats | `stats.py` | ⚠️ partial |
| `/status/performance`, heartbeat | `health` | ✅ |
| news | — | 🗑️ |

## Net read

The new grid **correctly sheds** most horde-isms (kudos, styles, gen-params,
teams/news) — chasing them would be a mistake. The parity items we actually care
about, in priority order:

1. **Content safety + IP/abuse controls** — ❌ blocking for public.
2. **Shared keys / multi-tenant API keys** — ❌ if B2B matters.
3. **Operator controls** (per-worker maintenance/pause) — ⚠️.
4. **Priority / QoS model** — ⚠️.
5. **Abuse/suspicion scoring** — ⚠️.
6. Interrogation, OAuth — ❌ minor / nice-to-have.
