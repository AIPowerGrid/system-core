# SPDX-FileCopyrightText: 2026 AI Power Grid
# SPDX-License-Identifier: AGPL-3.0-or-later

"""/v1/videos/generations — text-to-video generation.

Mirrors the image endpoint (there is no OpenAI standard here, so we keep the
same shape for consistency). Jobs go onto the media Redis Stream with
job_type=video and are served by media workers that support temporal models
(e.g. LTX). den scales per frame-step on the worker side.
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

logger = logging.getLogger("grid_api.videos")

router = APIRouter()


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt: str
    model: Optional[str] = None
    n: int = Field(default=1, ge=1, le=2)
    size: str = "768x512"
    seconds: float = Field(default=4.0, ge=1, le=10)
    fps: int = Field(default=24, ge=8, le=30)
    response_format: Optional[str] = "url"  # "url" | "b64_json"


@router.post("/v1/videos/generations")
@limiter.limit("4/minute")
async def create_video(
    request: Request,
    body: VideoRequest,
    apikey: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Text-to-video generation (grid-native, OpenAI-style envelope)."""
    try:
        key = extract_api_key(apikey, authorization)
        user = await accounts_svc.authenticate(key)

        model = body.model or media.DEFAULT_VIDEO_MODEL

        available = await get_available_models(job_type="video")
        if not available:
            raise HTTPException(status_code=503, detail="No video workers are online.")
        if model not in available:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model}' is not available. Online video models: {available}",
            )

        await quota.check_and_consume(dict(user))

        width, height = media.parse_size(body.size, default=(768, 512))
        frames = min(int(body.seconds * body.fps), media.MAX_FRAMES)
        extra = body.model_dump(exclude={"prompt", "model", "n", "size", "seconds", "fps", "response_format"})
        steps, cfg_scale, sampler = media.diffusion_params(model, extra)

        payload = {
            "prompt": body.prompt,
            "n": body.n,
            "width": width,
            "height": height,
            "frames": frames,
            "fps": body.fps,
            "steps": steps,
            "sampler_name": sampler,
            "cfg_scale": cfg_scale,
            "ext": "mp4",
        }
        for k in ("seed", "negative_prompt"):
            if extra.get(k) is not None:
                payload[k] = extra[k]

        outputs = await media.submit_and_wait(model, "video", payload, media.VIDEO_TIMEOUT)

        want_b64 = body.response_format == "b64_json"
        data = []
        for o in outputs:
            if want_b64:
                data.append({"b64_json": await media.url_to_b64(o["url"])})
            else:
                data.append({"url": o["url"]})

        return {"created": int(time.time()), "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error while processing the request.")
