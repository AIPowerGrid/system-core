# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Recipe resolver — the governed graph layer for media generation.

A *recipe* is an on-chain-approved ComfyUI workflow (RecipeVault on Base). Clients
never send graphs; they pick a recipe (by name/root) and supply inputs (prompt,
seed, image, dims). This module:

  - caches approved recipes (synced from RecipeVault, off the hot path),
  - resolves a recipe + client inputs into a concrete ComfyUI graph to dispatch.

Recipe metadata (which node slots are variable, clamp ranges, determinism, required
models, job type) rides in a `_grid` block inside the stored workflow JSON — so v1
needs ZERO contract change (the contract already stores the workflow). See
docs/architecture/RECIPE_DISPATCH.md.

SECURITY: inputs are injected into *parsed* node-input slots, never string-formatted
into the JSON. A prompt full of quotes/braces is just a dict value — it cannot alter
graph structure. Only recipes present in the cache (i.e. approved) can be resolved.
"""

import copy
import json
import logging
import os
import secrets
import zlib
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("grid_api.recipes")


@dataclass
class Recipe:
    recipe_root: str                 # bytes32 hex (content hash) — canonical id
    recipe_id: Optional[int]         # convenience alias (RecipeVault sequential id)
    name: str
    graph: dict                      # ComfyUI API graph (the `_grid` block stripped out)
    vars: dict[str, str]             # input name -> "nodeId.inputs.field"
    clamps: dict[str, list]          # numeric input name -> [lo, hi]
    deterministic: bool = False
    required_models: list[str] = field(default_factory=list)
    job_type: str = "image"          # image | video


# recipe_root (lower hex) -> Recipe ; plus an id index for convenience refs.
_BY_ROOT: dict[str, Recipe] = {}
_BY_ID: dict[int, Recipe] = {}


# ── registry ─────────────────────────────────────────────────────────────────
def register_recipe(recipe_root: str, name: str, workflow: dict, *,
                    recipe_id: Optional[int] = None) -> Recipe:
    """Add/replace a recipe in the cache. `workflow` is the full stored graph,
    including its `_grid` metadata block (which is split out here)."""
    meta = dict(workflow.get("_grid") or {})
    graph = {k: v for k, v in workflow.items() if k != "_grid"}
    r = Recipe(
        recipe_root=recipe_root.lower(),
        recipe_id=recipe_id,
        name=name,
        graph=graph,
        vars=dict(meta.get("vars") or {}),
        clamps=dict(meta.get("clamps") or {}),
        deterministic=bool(meta.get("deterministic", False)),
        required_models=list(meta.get("requiredModels") or []),
        job_type=str(meta.get("jobType") or "image"),
    )
    _BY_ROOT[r.recipe_root] = r
    if recipe_id is not None:
        _BY_ID[recipe_id] = r
    return r


def get_recipe(ref: str | int) -> Optional[Recipe]:
    """Look up by recipe_root (hex str) or recipe_id (int or numeric str)."""
    if isinstance(ref, int):
        return _BY_ID.get(ref)
    s = str(ref)
    if s.lower() in _BY_ROOT:
        return _BY_ROOT[s.lower()]
    if s.isdigit():
        return _BY_ID.get(int(s))
    return None


def list_recipes() -> list[Recipe]:
    return list(_BY_ROOT.values())


# ── resolution (the safe part) ───────────────────────────────────────────────
class RecipeError(Exception):
    """Recipe not found/approved, or inputs invalid."""


def _set_slot(graph: dict, slot: str, value: Any) -> None:
    """Set graph[node]['inputs'][field] for slot 'node.inputs.field'. Operates on
    the parsed dict — never string substitution."""
    parts = slot.split(".")
    if len(parts) != 3 or parts[1] != "inputs":
        raise RecipeError(f"bad slot spec '{slot}' (want 'nodeId.inputs.field')")
    node_id, _, field_name = parts
    node = graph.get(node_id)
    if not isinstance(node, dict) or "inputs" not in node:
        raise RecipeError(f"slot '{slot}' targets missing node/input")
    node["inputs"][field_name] = value


def _clamp_num(value: Any, lo: float, hi: float) -> float | int:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise RecipeError(f"expected a number, got {value!r}")
    v = max(lo, min(hi, v))
    return int(v) if float(v).is_integer() else v


# Inputs that are images must be a grid-issued upload id/ref, never an arbitrary
# URL (kills SSRF via inputs). The dispatch layer resolves the id to bytes.
_MAX_PROMPT_CHARS = 8000


def resolve(ref: str | int, inputs: dict | None = None) -> dict:
    """Resolve an approved recipe + client inputs into a concrete dispatch spec.

    Returns: {recipe_root, name, job_type, deterministic, seed, graph, required_models}
    Raises RecipeError if the recipe isn't approved/cached or inputs are invalid.
    """
    inputs = dict(inputs or {})
    r = get_recipe(ref)
    if r is None:
        raise RecipeError(f"recipe '{ref}' is not approved / not in the vault")

    graph = copy.deepcopy(r.graph)

    # Seed: first-class. Default to a fresh one; always echo back (for NFT repro).
    seed = inputs.get("seed")
    if seed in (None, "", 0):
        seed = secrets.randbelow(2**53)
    inputs["seed"] = int(seed)

    for name, slot in r.vars.items():
        if name not in inputs:
            continue
        val = inputs[name]
        if name in r.clamps:                      # numeric, clamped
            lo, hi = r.clamps[name]
            val = _clamp_num(val, lo, hi)
        elif name == "prompt" or name == "negative_prompt":
            val = str(val)[:_MAX_PROMPT_CHARS]
        # image inputs: caller must pass a grid upload ref; validated upstream.
        _set_slot(graph, slot, val)

    return {
        "recipe_root": r.recipe_root,
        "recipe_id": r.recipe_id,
        "name": r.name,
        "job_type": r.job_type,
        "deterministic": r.deterministic,
        "seed": inputs["seed"],
        "required_models": r.required_models,
        "graph": graph,
    }


# ── on-chain sync (off the hot path; no-op until configured) ──────────────────
async def sync_from_recipevault() -> int:
    """Pull approved recipes from RecipeVault into the cache. Returns count synced.
    No-ops (returns 0) if BASE_RPC_URL / RECIPEVAULT_ADDRESS aren't set."""
    addr = os.getenv("RECIPEVAULT_ADDRESS") or os.getenv("GRID_DIAMOND_ADDRESS")
    rpc = os.getenv("BASE_RPC_URL")
    if not addr or not rpc:
        logger.info("RecipeVault not configured (RECIPEVAULT_ADDRESS/BASE_RPC_URL) — "
                    "cache has %d seeded recipe(s)", len(_BY_ROOT))
        return 0
    try:
        from web3 import Web3
        from .._abi import RECIPEVAULT_ABI  # loaded from core-integration-package/abis
    except Exception as e:
        logger.warning("RecipeVault sync deps unavailable (%s) — cache unchanged", e)
        return 0
    try:
        w3 = Web3(Web3.HTTPProvider(rpc))
        c = w3.eth.contract(address=w3.to_checksum_address(addr), abi=RECIPEVAULT_ABI)
        total = c.functions.getTotalRecipes().call()
        n = 0
        for rid in range(1, total + 1):
            rec = c.functions.getRecipe(rid).call()        # struct: see RecipeVault.sol
            root = rec[0].hex() if isinstance(rec[0], (bytes, bytearray)) else str(rec[0])
            name = rec[1]
            raw = c.functions.getRecipeWorkflow(rid).call()  # zlib/pako-compressed bytes
            workflow = json.loads(zlib.decompress(raw).decode("utf-8"))
            register_recipe("0x" + root if not str(root).startswith("0x") else root,
                            name, workflow, recipe_id=rid)
            n += 1
        logger.info("RecipeVault sync: %d recipes cached", n)
        return n
    except Exception as e:
        logger.error("RecipeVault sync failed: %s", e)
        return 0
