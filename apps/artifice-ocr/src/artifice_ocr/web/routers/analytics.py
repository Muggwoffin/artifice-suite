# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Analytics routes."""

from fastapi import APIRouter

from ..runtime import state

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/stats")
def analytics_stats() -> dict:
    return state.history.stats()
