"""指标导出路由。"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from steward.observability.metrics import render_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """导出 Prometheus 指标。"""
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
