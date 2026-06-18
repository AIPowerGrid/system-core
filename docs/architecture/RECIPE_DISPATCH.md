# Recipe Dispatch — governed ComfyUI media on the grid

Expansion of **ADR‑0003** (the graph layer lives at the grid, backed by RecipeVault).
This is the design contract for image + video generation. Build against this; keep it
current as the implementation lands.

## Goal

Two client surfaces over **one governed dispatch core**:

1. **OpenAI‑style** (`/v1/images`, `/v1/videos`) — the easy path (aigarth, aipg.chat, casual API).
2. **ComfyUI Cloud API mirror** (`/api/prompt`, `/ws`, `/api/upload/image`, `/api/view`, …) —
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

**GAP to close (contract change):** `ModelRegistry`/`ModelVault` has **no `deterministic`
flag** — capability flags are `inpainting/img2img/controlnet/lora/isNSFW` only. Add
`bool deterministic` (a.k.a. `strictReproducible`) to the `Model` struct, and have
`GridNFT.mintArtworkComplete` require `tier == STRICT ⇒ model.deterministic`. Without this,
"only deterministic models mint reproducible NFTs" is convention, not enforced.

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

## The hash gate (how raw‑graph submit stays governed)

`recipeRoot` = hash of the **normalized** graph (variable slots blanked). On `/api/prompt`:
blank the same slots in the client's graph, hash, compare to the vault. Match → run; the
client still varies prompt/seed/image freely (those are the slots). This gives full ComfyUI
client compatibility **and** the approved‑only guarantee.

> Normalization must be deterministic and canonical (stable key order, slot‑blanking rules)
> so client graph and stored recipe hash identically. This is the make‑or‑break detail —
> spec the canonicalization precisely and test it with known vectors.

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

- Only approved‑structure graphs run (hash gate) → no arbitrary‑graph RCE/SSRF from clients.
- Inputs are values only, into typed slots, clamped → no JSON/graph injection.
- Worker isolation still applies (egress lockdown, fs jail, presigned‑only creds) — see
  [SAFETY_MODEL.md](SAFETY_MODEL.md); raw‑graph trust is constrained to vault recipes.
- Recipe creation gated by role + creation‑time node‑allowlist review.

## What exists vs net‑new

- **Exists:** RecipeVault contract + SDK, `/v1/videos`, media job queue + WS worker dispatch,
  comfy‑bridge `ws_worker`, R2 presigned upload, requeue cap.
- **Net‑new:** recipe cache + resolver; deterministic graph canonicalization + hash gate;
  safe typed‑slot substitution; `/api/*` mirror surface + `/ws`; capability routing;
  per‑job‑type long lease + busy‑heartbeat; GPU‑seconds metering; recipe creation‑time validation.

## Phased rollout

- **P1 — Governed core.** Recipe cache+resolver, canonicalization+hash gate, safe substitution.
  Store gorgadon's LTX as a vault recipe. Worker → dumb executor (drop `model_mapper`). Prove
  `/v1/videos` end‑to‑end on the recipe path.
- **P2 — Long‑video + mirror.** Async + per‑recipe lease + busy‑heartbeat + progress; then the
  ComfyUI Cloud mirror surface (`/api/prompt` hash‑gate, `/ws`, upload/view, `object_info`).
- **P3 — Trust + scale.** Capability routing, GPU‑seconds metering, validator re‑hash/sampling,
  recipe creation‑time allowlist. Retire `model_mapper` everywhere.

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

- **Add `deterministic` flag to `ModelRegistry`/`ModelVault`** + gate `GridNFT` STRICT mint on
  it (contract change — the gap found above).
- **Validate cross‑hardware determinism** for STRICT models across worker GPU classes, or
  restrict STRICT minting to a validated hardware tier.
- Recipe metadata home: extend the contract (`templateVars`/`requiredModels`/`requiredNodes`)
  vs a convention embedded in the stored graph.
- Whether to merge ModelVault ↔ RecipeVault (a model ≈ a recipe's required weights).
- Worker trust at launch: permissionless‑with‑bond is safe for deterministic models
  (re‑exec catches cheating); confirm same for non‑deterministic (bond + sampling).
