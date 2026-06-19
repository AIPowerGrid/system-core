# Grid Core — what the network is

The north‑star framing. Read this first; the other docs are the detail.

> **The AI Power Grid is a faithful, multi‑protocol, decentralized GenAI network.**
> Agentic‑native text (Anthropic **Messages** + OpenAI **Responses** first‑class;
> chat **completions** for compat) **and** media (image/video via on‑chain **recipes**).
> Every protocol is **passthrough‑faithful** and **tee‑metered**, routed to **bonded
> workers by capability**, **settled on‑chain**; deterministic recipes mint
> **reproducible NFTs**; **content safety** wraps all of it.
> Engines (vLLM, ComfyUI) are implementation details — clients speak whatever modern
> API they like; workers run whatever produces the result.

## Identity (what we are / are NOT)
- **Are:** a protocol‑pluralist decentralized inference + generation network with
  on‑chain governance, provenance, and economics.
- **Are NOT:** an OpenAI clone, a ComfyUI clone. We *speak* those protocols; we aren't them.

## The surfaces (one `/v1`, many protocols)
| Surface | Status | Notes |
|---|---|---|
| `POST /v1/messages` (Anthropic) | **first‑class** | tool use, thinking, citations, multimodal |
| `POST /v1/responses` (OpenAI) | **first‑class** | agentic; **stateless v1**, coordinator‑stored state later |
| `POST /v1/chat/completions` | compat | lowest common denominator; kept, not promoted |
| `POST /v1/images`, `/v1/videos` | **first‑class** | the selected "model" is an on‑chain **recipe** |

## Core decisions (locked)
1. **Faithful passthrough per protocol** — tunnel the native request to a worker that
   speaks it; tee the stream for metering. **No lossy canonical internal form** (that
   would destroy thinking / built‑in tools / structured outputs — the reason to lean
   into Messages/Responses at all).
2. **Messages + Responses first‑class; completions compat.**
3. **Responses statefulness: stateless v1** (`store:false`, no `previous_response_id`);
   coordinator‑stored state is a later add.
4. **Capability routing includes protocol** — a worker advertises which it serves
   (`messages`/`responses`/`chat`/`image`/`video`) + which models/recipes; the grid
   routes accordingly.
5. **Media is recipe‑governed** — the selectable "model" resolves to an on‑chain
   approved recipe; bonded workers are dumb executors. **No ComfyUI client mirror, no
   raw‑graph acceptance** (deliberately dropped — hollow under governance, fragile).
6. **Coordinator is trust‑minimized, not trustless** — open‑source, on‑chain settlement
   so it can't steal funds, content‑accountable (legally necessary for media). Decentralize
   compute + economics + governance; keep coordination + moderation accountable.

## The shared spine (same for text + media)
- **Governance on‑chain:** approved recipes (RecipeVault) + models (ModelRegistry/ModelVault).
- **Economics:** free tier + credits, **GPU‑seconds metering**, on‑chain Merkle settlement,
  worker **bonding/slashing**.
- **Verification (tiered by determinism):** re‑execution for deterministic recipes;
  economic + sampling + reputation otherwise; TEE on the roadmap (most operators lack it).
- **NFTs:** deterministic `(model, recipe, seed)` → reproducible on‑chain mint (GridNFT).
- **Safety:** prompt + output moderation + CSAM backstop — mandatory for generative media.

## Engines (pluralist, not ComfyUI‑centric)
A recipe declares its **`engine`**; the worker runs the engine‑specific `spec`:
- `comfyui` — spec = ComfyUI API graph (primary; the ecosystem).
- `drawthings` — spec = Draw Things params (Mac/Apple‑silicon).
- `native-ltx` / `vllm` / … — future, additive.
The resolver injects inputs by a dotted **var‑map** that works for nested (ComfyUI)
*and* flat (Draw Things) specs. ComfyUI is the *engine*, never baked into the protocol.

## Worker tiers & fair metering
Workers vary ~100× (RTX 5090 vs Apple‑silicon Draw Things vs old GPUs). Two things
must account for that: **routing** and **pay**.

- **Performance tiers** (per worker, per engine/job‑type): **fast** (interactive, high‑end
  GPU), **bulk** (throughput/async, mid), **slow** (capable‑but‑slow — Macs/Draw Things,
  old GPUs; overflow / non‑urgent / cheap). Plus capability flags: video‑capable, max
  resolution, max frames, engines supported.
- **Tiers are validator‑attested, not self‑declared.** Validators already re‑execute
  deterministic recipes to verify output — they **measure throughput in the same pass** and
  attest a tier. Self‑declared at first, validator‑corrected; claim "fast" but measure
  "slow" → re‑tiered / slashed. Trust‑minimized, reuses the validator role + bond.
- **Routing** matches a job's SLA (interactive vs batch) + requirements (video, resolution)
  to tier + engine + capability. A 5‑min‑on‑a‑5090 video doesn't go to a Mac unless it's a
  batch job that tolerates it.
- **Metering = work done, NOT wall‑clock.** Pay **hardware‑neutral work units** —
  megapixel‑steps (image), frame‑seconds (video) — at a per‑unit rate. Raw GPU‑seconds would
  **overpay slow hardware** for the same output. Tiers affect routing + a latency/SLA
  premium, not the base reward‑per‑work. *(Corrects the earlier "GPU‑seconds" note in
  RECIPE_DISPATCH.)*

## Detail docs
- [RECIPE_DISPATCH.md](RECIPE_DISPATCH.md) — media: recipe‑by‑reference, determinism tiers, NFTs, long‑video.
- [SAFETY_MODEL.md](SAFETY_MODEL.md) — content safety (defense‑in‑depth, validator role).
- [FOUNDATION_REVIEW.md](FOUNDATION_REVIEW.md) — grid_api health + the public‑utility properties.
- [PARITY_MATRIX.md](PARITY_MATRIX.md) — vs legacy horde.
