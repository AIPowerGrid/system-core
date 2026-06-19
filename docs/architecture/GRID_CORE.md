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

## Detail docs
- [RECIPE_DISPATCH.md](RECIPE_DISPATCH.md) — media: recipe‑by‑reference, determinism tiers, NFTs, long‑video.
- [SAFETY_MODEL.md](SAFETY_MODEL.md) — content safety (defense‑in‑depth, validator role).
- [FOUNDATION_REVIEW.md](FOUNDATION_REVIEW.md) — grid_api health + the public‑utility properties.
- [PARITY_MATRIX.md](PARITY_MATRIX.md) — vs legacy horde.
