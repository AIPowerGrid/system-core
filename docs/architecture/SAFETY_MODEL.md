# Content-Safety Model — now → decentralized future

Answers the question: *we can run CLIP (or any classifier) in the datacenter today —
how do we do safety in the future? Do we give the role to trusted validator nodes?*

**Short answer: partially. Validators become the decentralized *audit + slashing*
layer that keeps edge workers honest — but safety can NOT be purely validator-gated.
Two reasons that never go away: latency (prompt blocking must be instant, pre-dispatch)
and legal liability (it stays with the operator no matter who ran the classifier).
So the design is defense-in-depth with a mandatory centralized CSAM backstop, not
delegation.**

## Why safety ≠ compute verification

It's tempting to treat safety like correctness: let validators re-run and slash
liars. But safety has properties that break that model:

| | Compute correctness | Content safety |
|---|---|---|
| Truth | objective, reproducible (re-run, compare) | a policy judgment that evolves |
| Cost of a miss | a wrong pixel; refund | CSAM = criminal/existential |
| Timing | post-hoc is fine | prompt block must be **pre-dispatch**, instant |
| Liability | economic | **legal, and lands on the operator** |

You cannot slash your way out of a CSAM charge. Therefore validators *reduce load*
and *add trust*, they don't *replace* the operator's duty. Safety is layered.

## The layers (defense-in-depth)

```
request ─▶ L0 deterministic filter ─▶ L1 prompt classifier ─▶ dispatch ─▶ worker
                                                                            │
 serve/store ◀─ L4 CSAM backstop ◀─ L3 validator re-screen ◀─ L2 output classifier (at edge)
```

- **L0 — Deterministic prompt filter** (always, at the coordinator, microseconds):
  regex/blocklist for known-bad terms + the RecipeVault recipe allowlist. Port of
  the horde's `detection.py`. Runs at the grid edge because that's the choke point.
  Centralized forever — it's cheap and it's the legal floor.
- **L1 — Prompt classifier** (model; CLIP/text-classifier): blocks before any worker
  sees the prompt. **Today: runs in your datacenter** as a grid-internal service.
- **L2 — Output classifier** (model; NSFW/CSAM image classifier on results before
  return/store): catches benign-prompt→bad-output and evasion. Today: datacenter;
  tomorrow: pushed to the worker edge (see evolution).
- **L3 — Validator re-screen** (decentralized, sampled): validators re-run the
  approved safety classifier on a random N% of jobs; mismatch ⇒ the worker is
  slashed. This is where validator nodes earn their safety role.
- **L4 — CSAM backstop** (mandatory, centralized, never removed): a final cheap
  deterministic + classifier check at the coordinator on the highest-stakes category
  before anything is served or stored. Legal liability cannot be delegated, so this
  stays even at full decentralization.

## Tie safety into the existing on-chain spine

Safety reuses the same primitives as the rest of the grid — don't invent a parallel
trust system:

- **Approved safety models live on-chain** (a `SafetyModelVault`, or a category in
  ModelVault): everyone runs the *same approved classifier + threshold*, auditable
  and content-hashed. This is what makes L1–L4 agree on "what is a violation."
- **Bonding/slashing (#59)** is the enforcement: a worker that passes content it
  should have blocked is slashed harder than for a compute fault — and ejected for
  CSAM, not just penalized.
- **Validators (#51)** gain a safety-audit duty alongside compute spot-checks. Their
  attestations and the worker's safety attestation are signed and content-reference
  the approved model hash.
- **Governance** decides the blocklist/threshold/approved-models — same role layer
  that approves recipes (multisig → DAO).

## Trust model for safety validators (the nuance)

Safety validators are **higher-trust than compute validators**:

- Higher bond, and initially **foundation-operated / KYC'd** operators — you do not
  hand "decide what's legal" to an anonymous node on day one.
- **Consensus for contested cases**: m-of-n safety validators must agree before a
  borderline item is allowed (fail-closed on disagreement for high-stakes
  categories).
- **Asymmetric slashing**: false-negatives on CSAM are catastrophic, so the penalty
  for *passing* prohibited content ≫ the penalty for over-blocking. Bias the whole
  system toward false-positives.
- The coordinator's **L4 CSAM backstop overrides** any validator verdict. Validators
  can be wrong or malicious; the legal floor cannot depend on them.

## Evolution path

- **Phase A — now (centralized):** L0 deterministic + L1 prompt classifier + L2
  output classifier, all in the datacenter at the coordinator. Simple, controlled,
  legally clean. **This is the blocking gate for public launch.**
- **Phase B — edge attestation:** push L2 (and optionally L1) into the worker runtime
  as a *mandatory* step; the worker signs an attestation "passed approved model
  `0x…`, score `s`". Coordinator keeps L0 + a sampled backstop. Reduces datacenter
  load.
- **Phase C — decentralized audit:** validators (#51) do L3 random re-screening +
  slashing; safety models approved on-chain; consensus for contested items. L4 CSAM
  backstop remains centralized.
- **Phase D — endgame (TEE):** workers run safety in-enclave with remote attestation
  → cryptographic proof the approved classifier actually ran on the actual output.
  This is the point where safety can be *most* decentralized, because enclave
  attestation replaces operator trust — yet even here, keep L4 for legal cover.

## Decision (ADR-0002)

Content safety is defense-in-depth. Validators are the decentralized audit + slashing
layer (Phase C onward), **not** the gate. L0 deterministic filter and L4 CSAM
backstop are **mandatory and centralized at the coordinator, permanently**, because
prompt-blocking latency and legal liability cannot be delegated. Approved safety
models, bonding/slashing, and validator attestation reuse the existing on-chain spine.

## Immediate TODO (Phase A — blocking for public)

- [ ] Port the horde's deterministic prompt filter (`detection.py`) → grid L0, wired
      pre-dispatch in `routers/` + `services/media.py`.
- [ ] Stand up the CLIP/classifier service (datacenter) for L1 prompt + L2 output.
- [ ] IP-abuse controls (port `countermeasures.py` essentials): timeouts, blocks,
      suspicion counter — Redis-backed.
- [ ] Define the prohibited-content policy + the approved-safety-model list (even if
      off-chain at first; on-chain in Phase C).
- [ ] Asymmetric slashing schedule for safety failures in the WorkerRegistry.
