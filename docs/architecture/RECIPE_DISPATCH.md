# Recipe Dispatch — governed ComfyUI media on the grid

Expansion of **ADR‑0003** (the graph layer lives at the grid, backed by RecipeVault).
This is the design contract for image + video generation. Build against this; keep it
current as the implementation lands.

> **SUPERSEDED (see [GRID_CORE.md](GRID_CORE.md), decision 5):** the **ComfyUI client
> mirror / raw‑graph acceptance is dropped.** The client surface is **OpenAI‑style
> `/v1/images|videos` only**, where the selected "model" is an on‑chain recipe
> (recipe‑by‑reference). ComfyUI is the *worker engine*, not a client API. The
> "Surface 2 / hash‑gate / canonicalization" sections below are retained for history
> but are NOT being built. Everything else (recipe governance, determinism tiers,
> safe substitution, NFTs, long‑video, metering) stands.

## Goal

Client surface = **OpenAI‑style `/v1/images`, `/v1/videos`** over **one governed
dispatch core**. (Historical: the doc below also described a ComfyUI mirror —
superseded per the banner above.)

1. **OpenAI‑style** (`/v1/images`, `/v1/videos`) — the path (aigarth, aipg.chat, API, SDK).
2. ~~**ComfyUI Cloud API mirror**~~ (`/api/prompt`, `/ws`, `/api/upload/image`, `/api/view`, …) — DROPPED;
   the power/tooling path, so existing ComfyUI clients work almost unchanged.

Both resolve to a **concrete, RecipeVault‑approved ComfyUI graph** dispatched to a worker
that just executes it. `model_mapper` and per‑worker curated workflow files are retired.

## Principle: clients never run arbitrary graphs

The only graphs that execute are ones whose **structure** matches an approved recipe in the
on‑chain RecipeVault. Clients control *input values* (prompt/seed/image/size), never graph
*structure*. This is the security boundary and the trust primitive.

## The dispatch core (shared by both surfaces)

```
resolve → validate → substitute → route → execute → deliver
```

1. **resolve** — produce a candidate ComfyUI **API‑format** graph + the recipe it claims.
   - `/v1/*`: `model → recipe` lookup → recipe's graph.
   - `/api/prompt`: client sent the graph directly.
2. **validate** — normalize the graph (blank the variable slots) → hash → must equal an
   approved `recipeRoot` in the cached RecipeVault. No match → `403 workflow not approved`.
3. **substitute** — inject the client's inputs into the recipe's **typed node‑input slots**
   by the recipe's declared variable map. **Never string‑replace JSON** (injection hole).
   Clamp numerics (steps/frames/resolution) to the recipe's allowed ranges.
4. **route** — pick a worker whose advertised capability (models + custom nodes) covers the
   recipe's `requiredModels`/`requiredNodes`. None → `503 no capable worker`.
5. **execute** — worker POSTs the concrete graph to local ComfyUI `/prompt`, runs, collects
   outputs (image / **video** / audio), uploads to a grid‑issued presigned R2 slot.
6. **deliver** — grid returns the CDN URL; client polled status or watched `/ws`.

Worker = **dumb executor**: receive concrete graph → run → upload. No recipe knowledge, no
`model_mapper`, no local workflow files. (It may verify `recipeRoot` for integrity.)

## RecipeVault — the allowlist (already on‑chain)

- Grid Diamond on Base; `RecipeVault` module `0x58Dc9939FA30C6DE76776eCF24517721D53A9eA0`.
  Recipe = `{recipeRoot (content hash), name, compressed ComfyUI API graph, canCreateNFTs,
  isPublic}`; writes gated by `RECIPE_CREATOR_ROLE`.
- system‑core keeps a **local cache** (`recipeRoot → {graph, templateVars, requiredModels,
  requiredNodes}`), refreshed on `RecipeAdded` events / interval — **never read chain on the
  hot path** (same rule as ModelVault).
- **Recipe shape additions needed** (contract or convention inside the graph):
  `templateVars` (slot map: which node input ← which client field), `requiredModels`,
  `requiredNodes`. Drives substitution + routing.
- **Creation‑time gate:** a node‑allowlist + static validation must run before
  `storeRecipe` — "approved on‑chain" must mean "reviewed safe," not just signed.

## Determinism, NFTs & tiered verification (the core insight)

Verifiability depends on **determinism, which is a per‑model property.** Some models
reproduce a given `(model, recipe, seed, params)` → the same image (pinned weights, sampler,
fp32, deterministic kernels); most video / some image models do not.

**On‑chain reproducible NFTs (the payoff of determinism).** `GridNFT` mints an artwork as the
tuple `(modelId → ModelRegistry, recipeId → RecipeVault, seed, steps, cfg, w, h, sampler,
scheduler, prompt)` + `ipfsHash`, with `ArtTier {STANDARD, STRICT}` (STRICT = byte‑identical
fp32) and `isReproducible`. For a deterministic model, the on‑chain tuple **regenerates** the
art — the NFT is fully reproducible from chain data; `ipfsHash` is the canonical render. This
is rare in the space and only works because `recipeId` and `modelId` resolve to **immutable
on‑chain content**.

**Verification is tiered by determinism:**
- **Deterministic model (STRICT):** a validator re‑runs `(model, recipe, seed, params)` and
  compares — **strong, cheap verification.** Eligible for on‑chain reproducible NFTs.
- **Non‑deterministic (STANDARD — most video):** can't re‑run‑and‑compare. Trust = bond/slash
  + perceptual/semantic spot‑checks + reputation; output is the stored `ipfsHash` artifact
  (not regenerable); TEE is the only path to true verification (roadmap; most operators lack
  TEE hardware today).

**Determinism is a property of the RECIPE, not the model.** The same model reproduces in one
workflow and not in another. A recipe is deterministic only if ALL of:
- its `modelId` resolves to **pinned, immutable weights** (content‑hashed in ModelRegistry),
- **every node** in its graph is in the **approved deterministic‑safe node set**,
- its **sampler + scheduler are deterministic** ones,
- **precision is pinned** (fp32 for STRICT), and seed is fixed.

**`GridNFT` STRICT mint gates on `recipe.deterministic`** (and the pinned model), NOT a model
flag — a deterministic model in a non‑deterministic graph must not mint a "reproducible" NFT.

### How determinism is established — v1 vs later (deliberately lean)

Recipe creation is **already permissioned** (`RECIPE_CREATOR_ROLE`), so v1 has a *curated* set
of recipes, not permissionless submission. That lets v1 be far simpler — and actually safer:

- **v1 — tested assertion.** A trusted creator runs the recipe twice **on the real worker
  fleet**, confirms byte/perceptual reproduction, and flags `recipe.deterministic = true`
  (recorded on‑chain). Tested‑then‑flagged **can't lie**; an automated classifier that
  *infers* determinism without running it would mint NFTs that don't regenerate (false
  confidence). No node registry needed yet — the permission gate is the security boundary.
- **Later — automated node registry.** When recipe authoring **opens to permissionless
  (bonded) creators**, add an off‑chain governed node allowlist with two flags: **SAFE**
  (no `exec`/SSRF/fs‑write — security; a non‑SAFE node never runs) and **DETERMINISTIC**
  (SAFE subset, no nondeterminism). A creation‑time validator then walks the graph and sets
  the flags automatically. Build this *when* you open authoring — not before (premature
  generality, the trap we cut from system‑core).

**The registry stays off‑chain; only the per‑recipe verdict is on‑chain.** Nothing reads a
node list on‑chain — NFT/verification/dispatch only need the recipe + its `deterministic`
flag + the pinned model. Don't bloat the chain with churning ComfyUI node types.

**Caveat to validate, not assume:** even fp32 isn't guaranteed byte‑identical across GPU
*architectures* (different SM counts → different reduction orders for some kernels). Before
promising STRICT reproducibility cross‑fleet, **test the deterministic models across the
actual worker hardware classes** — or restrict STRICT minting to a validated hardware tier.

## Storage (per the determinism tier)

- **Recipes — hybrid.** Deterministic / NFT‑able recipes live **on‑chain** in RecipeVault
  (so `recipeId` resolves to fixed content forever — required for reproducible NFTs).
  Non‑NFT / experimental / heavy (video) recipes may live **off‑chain by CID** (RecipeVault
  stores CID + metadata). This is the "deterministic on‑chain, others off‑chain" split.
- **Outputs — IPFS + CDN.** `ipfsHash` (already in `GridNFT`) for permanence/NFT; R2/CDN for
  fast serving. Deterministic outputs are also regenerable from chain as a backstop, so for
  STRICT NFTs storage is convenience, not load‑bearing.

## Primary path: recipe‑by‑reference (not raw‑graph hashing)

Clients **name the recipe** (`recipeId`/`recipeRoot`) + supply inputs; the grid runs the
stored approved recipe. This is the default for both surfaces — robust, no canonicalization
fragility. The ComfyUI mirror is ComfyUI‑*shaped* (submit/poll/`/ws`/view), not
arbitrary‑graph‑accepting.

> **Deferred (optional, with permissionless authoring):** accepting a raw graph on
> `/api/prompt` and hash‑matching it to an approved recipe (`recipeRoot` = hash of the
> normalized graph, variable slots blanked). Elegant for tooling, but cross‑version
> canonicalization is brittle — only build it if a real client needs to POST graphs, and
> spec the canonicalization with known‑vector tests first.

## Surface 1 — OpenAI‑style (keep)

- `POST /v1/images` `{model, prompt, n, size, image?}` → 202 `{id}` (async) or sync for fast image.
- `POST /v1/videos` `{model, prompt, image?, frames?, size?}` → **always async** `{id}`.
- `GET /v1/jobs/{id}` → `{status, progress, result_urls}`.
- Resolves `model → recipe` server‑side; otherwise identical to the core.

## Surface 2 — ComfyUI Cloud API mirror (new)

| Endpoint | Grid behavior | Notes |
|---|---|---|
| `POST /api/prompt` | hash‑gate the graph → enqueue → `{prompt_id}` | the gate |
| `GET /api/job/{id}/status` | grid job status | `pending/in_progress/completed/failed/cancelled` |
| `WSS /ws` | `executing` / `progress` / `executed` / `execution_error` (+ optional preview) | **key for 2–5 min video** |
| `POST /api/upload/image`, `/api/upload/mask` | store to R2 → `{name, subfolder}` | i2v start frame / mask |
| `GET /api/view?filename&subfolder&type` | 302 → R2/CDN | |
| `GET /api/object_info` | **aggregate** fleet capability (servable recipes/models/nodes) | adapted, not per‑node 1:1 |
| `GET/POST /api/queue`, `POST /api/interrupt` | scoped to the caller's **own** jobs | multi‑tenant |

**Auth:** accept both `X-API-Key` (Comfy style) and `Bearer` (grid keys).
**Not mirrored:** arbitrary‑graph execution (→ hash‑gated), cross‑tenant queue control, raw
per‑node `object_info`.

## Long jobs (video = 2–5 min) — first‑class

1. **Async by default for video**; submit returns immediately. Never hold the HTTP connection.
2. **Per‑recipe lease/timeout** (video ≈ 600s, tunable), separate from text/image.
3. **Busy ≠ dead:** worker heartbeats `processing job X, step k/total` so strike/eviction does
   NOT kill a mid‑render worker. (This exact failure mode bit text workers; fatal for video.)
4. **Progress passthrough:** ComfyUI step progress → bridge → `/ws` + `GET …/status`.
5. **Requeue only on real failure** (disconnect / hard timeout), bounded by the existing cap.
6. **Big outputs:** dedicated R2 bucket + CDN, longer TTL than transient images; preserve audio.

## Metering

Worker reports **GPU‑seconds** per job (LTX runtime varies wildly with length/res) → credits /
settlement (#58). A flat per‑video price mis‑charges badly. `recipeRoot` lets a validator
re‑hash + (sample) re‑execute to verify the worker ran the approved recipe → feeds slashing.

## Security summary

- Only **approved (vault) recipes** run; clients reference them, never submit graphs (v1) →
  no arbitrary‑graph RCE/SSRF.
- Inputs are values only, into typed slots, clamped → no JSON/graph injection.
- Worker isolation still applies (egress lockdown, fs jail, presigned‑only creds) — see
  [SAFETY_MODEL.md](SAFETY_MODEL.md).
- Recipe creation gated by `RECIPE_CREATOR_ROLE` (the curation IS the v1 security boundary);
  formal node allowlist arrives with permissionless authoring (P4).
- Content safety (prompt + output classifiers, CSAM backstop) wraps dispatch — mandatory for
  generative media (SAFETY_MODEL).

## What exists vs net‑new

- **Exists:** RecipeVault contract + SDK, GridNFT (recipe/model/seed + ArtTier + ipfsHash),
  `/v1/videos`, media job queue + WS worker dispatch, comfy‑bridge `ws_worker`, R2 presigned
  upload, requeue cap.
- **Net‑new (v1):** recipe cache + resolver; safe typed‑slot substitution; capability match;
  per‑job‑type long lease + busy‑heartbeat; `recipe.deterministic` flag + GridNFT STRICT gate.
- **Later:** ComfyUI‑shaped mirror + `/ws`; GPU‑seconds metering; validator re‑exec sampling;
  node registry + creation‑time validator (P4); optional raw‑graph hash‑gate.

## Minimal v1 contract diff (small on purpose)

- **RecipeVault:** add `bool deterministic` to the recipe record (set at store time by a
  trusted creator who tested reproduction). Keep storing the graph for on‑chain/NFT recipes;
  allow a CID variant for off‑chain ones.
- **ModelRegistry:** ensure model weights are **content‑hashed / pinned** (immutable ref) —
  reproducibility depends on it.
- **GridNFT:** require `tier == STRICT ⇒ recipe.deterministic` (read from RecipeVault).
- **Not now:** node registry contract, on‑chain node allowlists, hash‑gate canonicalization.

## Phased rollout (leaner v1)

- **P1 — Governed core (recipe‑by‑reference).** Recipe cache+resolver, **safe typed‑slot
  substitution** (no canonicalization/hash‑gate), capability match. Store gorgadon's LTX as a
  vault recipe. Worker → dumb executor (drop `model_mapper`). Prove `/v1/videos` end‑to‑end.
- **P2 — Long‑video + ComfyUI‑shaped mirror.** Async + per‑recipe lease + busy‑heartbeat +
  progress; then the mirror surface (`/api/job/.../status`, `/ws`, upload/view, `object_info`)
  — recipe‑referenced, not raw‑graph.
- **P3 — Trust + scale + NFTs.** GPU‑seconds metering; validator re‑exec sampling (re‑run
  deterministic recipes, compare); on‑chain reproducible NFT minting via GridNFT.
- **P4 — Permissionless authoring.** Off‑chain node registry (SAFE/DETERMINISTIC) +
  creation‑time validator; bonded recipe authors; optional raw‑graph hash‑gate. Build only here.

## Decisions — locked

- **Trust v1 = validator nodes + economic (bond/slash); TEE on the roadmap** (most operators
  lack TEE hardware). Verification is **tiered by determinism** (above): re‑execution for
  deterministic models, sampling/reputation for the rest.
- **Storage = hybrid recipes** (deterministic on‑chain / others off‑chain CID) **+ outputs on
  IPFS (`ipfsHash`) + CDN.**
- **No arbitrary‑graph hash‑gate as the primary path** — too fragile (cross‑version
  canonicalization). Default is **recipe‑by‑reference** (client names recipe id + inputs);
  the ComfyUI mirror is ComfyUI‑*shaped*, not arbitrary‑graph‑accepting.

## Open questions (decide before/inside each phase)

- **`deterministic` flag lives on the RECIPE** (not the model), set at creation by validating
  the graph against the **approved node registry** (SAFE + DETERMINISTIC allowlists) +
  deterministic sampler/scheduler/precision + pinned model. Gate `GridNFT` STRICT on it.
- **Build the node registry** — the SAFE allowlist is also the security gate (creation‑time
  node review); DETERMINISTIC is the STRICT‑eligibility subset. On‑chain vs off‑chain‑recorded.
- **Validate cross‑hardware determinism** for STRICT models across worker GPU classes, or
  restrict STRICT minting to a validated hardware tier.
- Recipe metadata home: extend the contract (`templateVars`/`requiredModels`/`requiredNodes`)
  vs a convention embedded in the stored graph.
- Whether to merge ModelVault ↔ RecipeVault (a model ≈ a recipe's required weights).
- Worker trust at launch: permissionless‑with‑bond is safe for deterministic models
  (re‑exec catches cheating); confirm same for non‑deterministic (bond + sampling).
