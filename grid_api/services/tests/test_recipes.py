# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the recipe resolver — safe substitution, clamping, seed, governance.

Pure stdlib; runnable with `python3 test_recipes.py` (no pytest/web3 needed)."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from grid_api.services import recipes  # noqa: E402


def _seed_ltx():
    """An LTX-like i2v recipe with a _grid metadata block."""
    recipes._BY_ROOT.clear(); recipes._BY_ID.clear(); recipes._BY_NAME.clear()
    workflow = {
        "_grid": {
            "vars": {
                "prompt": "6.inputs.text",
                "seed": "3.inputs.seed",
                "image": "10.inputs.image",
                "steps": "3.inputs.steps",
            },
            "clamps": {"steps": [1, 50]},
            "deterministic": False,
            "requiredModels": ["LTX-2.3"],
            "jobType": "video",
        },
        "3": {"class_type": "KSampler", "inputs": {"seed": 0, "steps": 20, "cfg": 3.5}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "PLACEHOLDER"}},
        "10": {"class_type": "LoadImage", "inputs": {"image": ""}},
    }
    return recipes.register_recipe("0xabc123", "LTX-2.3 i2v", workflow, recipe_id=1)


def test_basic_substitution():
    _seed_ltx()
    out = recipes.resolve("0xabc123", {"prompt": "a cat", "image": "upload_42", "seed": 7})
    g = out["graph"]
    assert g["6"]["inputs"]["text"] == "a cat"
    assert g["10"]["inputs"]["image"] == "upload_42"
    assert g["3"]["inputs"]["seed"] == 7
    assert "_grid" not in g                      # metadata stripped
    assert out["job_type"] == "video"
    assert out["required_models"] == ["LTX-2.3"]
    print("ok: basic substitution")


def test_injection_safe():
    _seed_ltx()
    nasty = '","class_type":"Evil"},"99":{"inputs":{},"x":"'   # graph-injection attempt
    out = recipes.resolve("0xabc123", {"prompt": nasty})
    g = out["graph"]
    assert g["6"]["inputs"]["text"] == nasty      # stored verbatim as a value
    assert "99" not in g                           # NO new node injected
    assert len(g) == 3                             # still exactly nodes 3,6,10
    # round-trips as valid JSON with structure intact
    assert json.loads(json.dumps(g))["6"]["inputs"]["text"] == nasty
    print("ok: injection-safe")


def test_clamp():
    _seed_ltx()
    assert recipes.resolve("0xabc123", {"steps": 9999})["graph"]["3"]["inputs"]["steps"] == 50
    assert recipes.resolve("0xabc123", {"steps": -5})["graph"]["3"]["inputs"]["steps"] == 1
    print("ok: clamp")


def test_seed_default_and_echo():
    _seed_ltx()
    out = recipes.resolve("0xabc123", {"prompt": "x"})
    assert isinstance(out["seed"], int) and out["seed"] > 0      # generated
    assert out["graph"]["3"]["inputs"]["seed"] == out["seed"]    # injected + echoed
    print("ok: seed default + echo")


def test_unapproved_rejected():
    _seed_ltx()
    try:
        recipes.resolve("0xdeadbeef", {"prompt": "x"})
        assert False, "should have raised"
    except recipes.RecipeError:
        print("ok: unapproved recipe rejected")


def test_lookup_by_id():
    _seed_ltx()
    assert recipes.resolve(1, {"prompt": "x"})["recipe_root"] == "0xabc123"
    print("ok: lookup by id")


def test_resolve_for_model_by_name():
    _seed_ltx()
    spec = recipes.resolve_for_model("LTX-2.3 i2v", {"prompt": "x"})  # by name (case-insensitive)
    assert spec and spec["recipe_root"] == "0xabc123" and spec["job_type"] == "video"
    print("ok: resolve_for_model by name")


def test_resolve_for_model_falls_back():
    _seed_ltx()
    assert recipes.resolve_for_model("some-unmapped-model", {"prompt": "x"}) is None
    print("ok: resolve_for_model returns None for unmapped (legacy fallback)")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nALL RECIPE TESTS PASSED")
