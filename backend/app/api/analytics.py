"""Productivity analytics with independent per-user data isolation."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..deps import DeviceDep, UserDep
from ..schemas import AnalyticsRead
from ..services import analytics as analytics_service

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsRead)
async def analytics(
    device: DeviceDep,
    user: UserDep,
    range_days: int = Query(default=7, ge=1, le=90),
) -> AnalyticsRead:
    return await analytics_service.build(device.id, range_days, user=user)
