# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later

"""OpenAI-compatible /v1/images/generations — native v2 media dispatch.

Jobs go onto the media Redis Stream and are served by WS-connected media
workers (same machinery as text/video). The worker uploads results directly to
R2 via presigned URLs; the completion arrives on the job's pub/sub channel.

Smart defaults for steps/cfg/sampler are derived from the model, but advanced
callers can override them (and pass seed / negative_prompt) — the schema allows
extra fields so power users get raw control while staying OpenAI-shaped.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import extract_api_key
from ..ratelimit import limiter
from ..services import accounts as accounts_svc
from ..services import media, quota
from .worker_ws import get_available_models

logger = logging.getLogger("grid_api.images")

router = APIRouter()


class ImageRequest(BaseModel):
    # Allow advanced passthrough params (seed, negative_prompt, steps, cfg_scale,
    # sampler) without dropping them — power users get raw control.
    model_config = ConfigDict(extra="allow")

    prompt: str
    model: Optional[str] = None
    n: int = Field(default=1, ge=1, le=4)
    size: str = "1024x1024"
    quality: Optional[str] = "standard"
    response_format: Optional[str] = "url"  # "url" | "b64_json"


@router.post("/v1/images/generations")
@limiter.limit("10/minute")
async def create_image(
    request: Request,
    body: ImageRequest,
    apikey: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """OpenAI-compatible image generation."""
    try:
        key = extract_api_key(apikey, authorization)
        user = await accounts_svc.authenticate(key)

        model = body.model or media.DEFAULT_IMAGE_MODEL

        # Fast availability check — fail in ms instead of waiting out the job
        # timeout when no worker serves the model.
        available = await get_available_models(job_type="image")
        if not available:
            raise HTTPException(status_code=503, detail="No image workers are online.")
        if model not in available:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model}' is not available. Online image models: {available}",
            )

        await quota.check_and_consume(dict(user))

        width, height = media.parse_size(body.size)
        extra = body.model_dump(exclude={"prompt", "model", "n", "size", "quality", "response_format"})
        steps, cfg_scale, sampler = media.diffusion_params(model, extra)

        payload = {
            "prompt": body.prompt,
            "n": body.n,
            "width": width,
            "height": height,
            "steps": steps,
            "sampler_name": sampler,
            "cfg_scale": cfg_scale,
            "ext": "webp",
        }
        # Pass advanced knobs through to the worker when provided.
        for k in ("seed", "negative_prompt"):
            if extra.get(k) is not None:
                payload[k] = extra[k]

        outputs = await media.submit_and_wait(model, "image", payload, media.IMAGE_TIMEOUT)

        want_b64 = body.response_format == "b64_json"
        data = []
        for o in outputs:
            if want_b64:
                data.append({"b64_json": await media.url_to_b64(o["url"]), "revised_prompt": body.prompt})
            else:
                data.append({"url": o["url"], "revised_prompt": body.prompt})

        return {"created": int(time.time()), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error while processing the request.")
