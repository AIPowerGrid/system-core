# Credits & settlement — the money pipeline (demand ↔ supply)

Status: **design, partially built (ship-dark).** This is the implementation-level
companion to [ECONOMICS.md](./ECONOMICS.md) (the macro: treasury, liquidity,
split, phasing). That doc decides *the numbers*; this one wires *the plumbing*:
how a consumer's payment becomes credits, becomes a metered charge, becomes
worker den, becomes an on-chain payout on Base.

Ties to tasks: #58 (charge model), #68 (per-account usage), #46 (contracts
hardening), #45 (settlement bot, done).

> **Design stance:** world-class but reality-grounded. We are a web3,
> decentralized GenAI network on Base. The meter and the payout are
> verifiable on-chain; everything that *can* be trust-minimized is. But AIPG is
> illiquid today (~$171k cap, ~$7/day vol — see ECONOMICS.md), so we do **not**
> design against a deep token market. Real revenue arrives in **USDC/fiat**;
> AIPG payouts are "network equity, cheap" until liquidity exists.

---

## 1. The one idea

**One balance. Many on-ramps. The ledger is the truth. Workers get paid from
work, on-chain, no matter how the consumer paid.**

Two accounting planes that never get confused:

| Plane | Unit | Who | Where it lives |
|---|---|---|---|
| **Demand** (what consumers pay) | **micro-USD credits** | API/chat/art users + agents | `credits` / `credit_ledger` (Postgres) |
| **Supply** (what workers earn) | **den** → **AIPG** | GPU operators | `grid_ledger.den` → Merkle root → Base |

The protocol sits in the spread between them (the 12% — funds free tier, infra,
buyback-burn). Keeping the planes separate is what lets fiat, USDC, and AIPG all
feed one system without an oracle on the hot path.

```
   CONSUMER PAYS                    METERED USE                 WORKER EARNS                SETTLED ON BASE
   ─────────────                    ───────────                 ────────────                ───────────────
   Stripe (USD) ─┐                                              den per job                 epoch Merkle root
   USDC  (Base) ─┼─► buy credits ─► debit micro-USD ─► job ───► (grid_ledger) ──► aggregate ──► reportPeriod
   AIPG  (Base) ─┘   (micro-USD)     per token×price            wallet-keyed       by wallet     + claimBatch
   x402 (USDC)  ─────────────────────────────────────►                                          → AIPG to worker
                                          │                                                          ▲
                                          └── 12% protocol margin ── 85% worker share ──► funds the RewardPool
```

---

## 2. What already exists (grounded in code)

This is further along than it looks — most pieces are built but **ship-dark**
(not wired into the request path).

| Piece | File | State |
|---|---|---|
| Prepaid credit ledger (idempotent `credit`/`debit`, overdraft-safe, charge gated by `GRID_CHARGING_ENABLED`) | `grid_api/services/credits.py` | **built, ship-dark** |
| Per-model price book (currently AIPG-native, "half cheapest competitor") | `grid_api/services/pricing.py` | **built, ship-dark** |
| Worker reward meter — server-side token count (anti-gaming), ModelVault size multipliers | `grid_api/services/den.py` | **live** (written per job) |
| Den roll-up by wallet for a period | `grid_api/services/settlement/aggregate.py` | **live** |
| Settlement bot (Merkle root, `reportPeriod`+`claimBatch`, dry-run, state cursor) | `grid_api/services/settlement/bot.py` | **built, dry-run ready** |
| Go-live runbook (contracts deployed+verified on Base) | `grid_api/services/settlement/GO_LIVE.md` | **ready to run** |
| Tables `credits`, `credit_ledger`; `grid_ledger` (den, wallet, duration, ttft) | `v2/schema.py`, `alembic/0002_credits.py`, `0004_ledger_timing.py` | **migrated** |

On-chain (Base, from GO_LIVE.md): Grid diamond `0x79F3…c609`, AIPG token
`0xa1c0…4608`, RewardPool `0x973a…5082`, DenReporter `0xf06d…0fd5`,
PaymentRouter `0x3fF2…c65A`. State: cut ✓, not paused ✓, `poolBalance=0`,
`periodLength=86400`.

**The two real gaps:**
1. **Demand side is dark** — `credits.py`/`pricing.py` aren't called on the request
   path, and the ledger doesn't record the *consuming* `account_id` (only the
   *earning* worker wallet). So no per-account usage, no charging. (= task #68,
   and the console's dashed "Usage by Key" cards.)
2. **Supply ≠ revenue yet** — settlement pays a *fixed* `periodAllocation` from a
   seeded pool (emission-style). Nothing routes consumer revenue into the pool.
   The **revenue→pool bridge** is the core new build.

---

## 3. Key design decisions

1. **Denominate credits in micro-USD.** USDC *is* a dollar on Base, so USD-denom is
   natural here, not a compromise. Pricing already comes from a USD competitor
   sheet — charge `tokens × usd_price` directly and the per-request oracle
   *disappears*. (Action: retarget `pricing.py`/`credits.py` from micro-AIPG to
   micro-USD; the module docstrings currently disagree — `credits.py` says both —
   resolve to USD.)
2. **Oracle only at the edges, never per request.** A USDC deposit credits 1:1. An
   AIPG deposit converts AIPG→USD *once, at deposit time* (+ discount). The
   revenue→pool conversion (USD→AIPG) happens *once per epoch*. The hot path
   touches no price feed.
3. **Credits are non-refundable service credits** — not withdrawable, not cash-like.
   This is the line that keeps us out of money-transmitter / stored-value
   territory. Stripe sells *API credits*, not crypto.
4. **Idempotency end-to-end** (already true in `credits.py`): every top-up and every
   charge keys on a unique `ref`, so a retried request or re-seen deposit/webhook
   can't double-bill or double-credit.
5. **Verifiable supply side.** Den is metered server-side (workers can't inflate),
   rolled into a Merkle root, and paid on-chain — anyone can verify a worker got
   paid. Hardening (validator co-sign of roots) tracked in validator-node + #46.
6. **Agent-native by design.** x402 (HTTP 402 + USDC on Base) is a first-class
   consumer path, not a bolt-on: an autonomous agent pays per call with no
   account. It still meters to den exactly like a prepaid request.

---

## 4. Economics (numbers live in ECONOMICS.md — referenced, not redefined)

- **Pricing:** ~50% under the cheapest competitor, per model (`pricing.py`).
- **Split (per ECONOMICS.md):** **85% Generator (worker) / 3% Sentinel / 12%
  protocol**, of which ~half → AIPG buyback-burn. Make it a governance param.
- **Free tier funding:** free-tier jobs **still earn workers den** — workers are
  paid for that work too. That den is subsidized from the 12% / pool. This is the
  literal mechanism behind "paid users fund the free tier."
- **AIPG payment = discount = token sink:** pay in AIPG, get +X% credits. The
  discount is funded as token-incentive spend (treasury/tokenomics), not from
  margin. Creates real buy pressure. **Cap AIPG top-ups** until liquidity exists
  (thin pool — see ECONOMICS.md).
- **Bootstrap vs revenue phase (honest):** today, AIPG payouts are emission-funded
  "cheap equity," and security rests on the **verification layers**, not economic
  stake. Revenue-funded payroll (below) is the transition to real income.

---

## 5. The revenue→pool bridge (the core new build)

Connects the two planes. Each epoch:

```
net_revenue_usd  = credits spent this epoch  (from credit_ledger debits)
worker_pool_usd  = net_revenue_usd × 0.85
allocation_aipg  = worker_pool_usd / aipg_usd_price        # one oracle read / epoch
→ deposit/allocate allocation_aipg into RewardPool (setPeriodAllocation)
→ settlement bot splits it pro-rata by den (existing path)
protocol_12%     → free-tier subsidy + infra + buyback-burn
```

Two ways to actually fund the AIPG payout, pick by phase:
- **Bootstrap:** treasury pre-seeds the pool; `allocation` tracks revenue but is
  paid from treasury AIPG (decentralizes the 70% founder hold — ECONOMICS.md).
- **Revenue-funded:** protocol uses USDC revenue to *buy* AIPG (→ the LP, helps
  liquidity) and funds the pool from purchases — "fiat→AIPG payroll" = usage-driven
  demand. This is Phase 2 in ECONOMICS.md (needs the LP seeded first).

---

## 6. Data model

```
accounts(account_id UUID pk, wallet, auth fields …)         -- consumers (v2)
credits(account_id pk, balance_micro BIGINT, updated)        -- micro-USD balance
credit_ledger(id, account_id, delta_micro, reason, ref UNIQUE, model, created)
grid_ledger(id, …, model, den FLOAT, wallet, duration, ttft, created)
            -- supply side; `wallet` = WORKER payee
```

**The attribution change (task #68):** add the *consuming* `account_id` (or
`api_key_hash`) to `grid_ledger`, or join via the job→account map. Without it we
can't show per-account usage *or* reconcile revenue. This single change unblocks:
the console's Usage/Spend cards, per-key metering, and the revenue side of the
bridge.

---

## 7. Two pragmatic tracks

These are independent — run them in parallel.

### Track A — get worker payments going (supply side, ~ready now)
Follow `settlement/GO_LIVE.md`. Money is an ops task away, not a build:
1. **Fix worker→wallet attribution** — `aggregate.py` excludes empty-wallet rows;
   if prod rows have NULL wallets, no one's payable. Verify with the step-0 SQL.
2. Provision a gas-only reporter hot wallet; grant `REPORTER_ROLE`.
3. Seed a **small** pool + tiny daily allocation (runbook suggests 5000/100 AIPG) —
   emission-funded bootstrap, proves the pipe.
4. **Dry-run** the bot against the last closed period; verify root + wallets.
5. Flip one period live; verify on-chain payout; hand to the daily systemd loop.

→ Workers start getting paid (network equity) **without** waiting on revenue.

### Track B — get funded (demand side)
1. **Wire credits dark** — call `charge_request` on the request path with
   `GRID_CHARGING_ENABLED=0`; it only logs what it *would* bill. Add `account_id`
   to the ledger (task #68). Observe against real traffic.
2. **USDC top-up on Base** via PaymentRouter → credits 1:1. Real revenue.
3. **Flip charging on** (`GRID_CHARGING_ENABLED=1`) once dry-run logs look right
   and balances reconcile. Free daily quota stays (Redis) for the free tier.
4. **Revenue→pool bridge** (§5): allocation tracks the 85% worker share.
5. **AIPG rail + discount** (token sink; capped).
6. **Stripe** (fiat — biggest TAM, biggest compliance lift: treasury conversion,
   chargeback rules).
7. **x402 pay-per-call** (agent-native, USDC).

---

## 8. Risks & guardrails

- **Compliance:** credits non-refundable / non-withdrawable; Stripe sells service
  credits, not tokens; no yield/return promises on AIPG.
- **AIPG volatility & illiquidity:** convert AIPG deposits at deposit time; cap
  AIPG top-up size; never hold volatile inventory against USD-denominated
  obligations. Don't price USD payouts off a $7/day pool.
- **Chargebacks (Stripe):** credits are prepaid; fraud rules + new-account limits;
  consumed inference is unrecoverable.
- **Reporter key compromise:** bounded to one period's allocation (keep allocation
  small until validator co-sign lands — GO_LIVE.md, #46).
- **Treasury custody:** move the 105M off a single Ledger to a Safe multisig; put
  contract-admin behind the Safe too (ECONOMICS.md, #46).
- **Double-spend / double-pay:** idempotent `ref` on both planes; settlement state
  cursor prevents double-report.

---

## 9. Open decisions (recommended defaults in **bold**)

1. Credit denomination: **micro-USD** / micro-AIPG.
2. Worker split: **85 / 3 / 12 per ECONOMICS.md** / other (governance param).
3. First payouts: **emission-funded bootstrap now**, revenue-funded after LP seed.
4. AIPG top-up cap: **start low (e.g. $50/tx)** given pool depth; raise with liquidity.
5. Settlement cadence: **daily (86400s, as deployed)**.
