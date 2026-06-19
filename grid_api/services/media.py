# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared media (image / video) generation helpers.

One code path behind three front doors: `/v1/images/generations`,
`/v1/videos/generations`, and the chat-completions abstraction. Each submits a
media job to the Redis media stream (served by ComfyUI/media workers that upload
to R2 and report back on the job channel) and waits for the result. den +
ledger are recorded by the worker WS handler, so callers never meter directly.
"""

import base64
import json
import logging
from uuid import uuid4

import httpx
from fastapi import HTTPException

from . import job_queue, token_stream

logger = logging.getLogger("grid_api.media")

DEFAULT_IMAGE_MODEL = "FLUX.2 [klein]"
DEFAULT_VIDEO_MODEL = "LTX-2.3"

# Output dimension clamps — a client must not be able to push an arbitrary size
# that ties up a GPU (or OOMs the worker).
MIN_DIM, MAX_DIM = 256, 1536
MAX_FRAMES = 240  # ~10s @ 24fps ceiling

IMAGE_TIMEOUT = 300
VIDEO_TIMEOUT = 600


def clamp_dim(v: int) -> int:
    """Clamp a dimension and snap to a multiple of 64 (diffusion-friendly)."""
    v = max(MIN_DIM, min(MAX_DIM, int(v)))
    return (v // 64) * 64 or MIN_DIM


def parse_size(size: str, default=(1024, 1024)) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in str(size).lower().split("x"))
        return clamp_dim(w), clamp_dim(h)
    except (ValueError, AttributeError):
        return default


def diffusion_params(model: str, overrides: dict) -> tuple[int, float, str]:
    """Pick sensible steps/cfg/sampler from the model, honoring explicit overrides.

    Advanced callers can pass `steps` / `cfg_scale` / `sampler` to override the
    smart defaults; the OpenAI-shaped path just omits them and gets the defaults.
    """
    name = model.lower()
    is_flux = "flux" in name
    is_fast = "klein" in name or "schnell" in name
    steps = overrides.get("steps") or (4 if is_fast else (20 if is_flux else 30))
    cfg = overrides.get("cfg_scale") or (1.0 if is_fast else (3.5 if is_flux else 7.5))
    sampler = overrides.get("sampler") or ("euler" if is_flux else "k_euler")
    return int(steps), float(cfg), str(sampler)


async def submit_and_wait(model: str, job_type: str, payload: dict, timeout: int) -> list[dict]:
    """Queue a media job and block until the worker reports the result.

    Returns the list of output objects ({url, key, sha256, seed}). Progress
    events on the channel are ignored; the DONE event carries the media JSON."""
    job_id = str(uuid4())
    await job_queue.submit_job(job_id, payload, [model], job_type=job_type)
    logger.info(f"{job_type} job {job_id} queued model={model}")

    async for event in token_stream.subscribe_tokens(job_id, timeout=timeout):
        if event.get("text") != token_stream.DONE_SENTINEL:
            continue  # progress event — skip
        if event.get("error"):
            raise HTTPException(status_code=event.get("code") or 502, detail=event["error"])
        try:
            result = json.loads(event.get("full_text") or "{}")
        except (TypeError, ValueError):
            raise HTTPException(status_code=500, detail="Malformed worker result")
        media = [o for o in result.get("media", []) if o.get("url")]
        if not media:
            raise HTTPException(status_code=502, detail="No media returned")
        logger.info(f"{job_type} job {job_id} done: {len(media)} output(s)")
        return media

    raise HTTPException(status_code=504, detail=f"{job_type} generation timed out")


async def url_to_b64(url: str) -> str:
    """Fetch a generated asset and base64-encode it (for response_format=b64_json)."""
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url)
        r.raise_for_status()
        return base64.b64encode(r.content).decode()
