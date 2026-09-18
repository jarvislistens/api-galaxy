"""Mission Mode endpoints. Answers are graded against the real graph, never a stored key."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api_galaxy.app.errors import NotFoundError
from api_galaxy.app.state import get_state
from api_galaxy.missions import MISSION_INDEX, evaluate, list_missions

router = APIRouter(prefix="/api/v1", tags=["missions"])


class MissionAttempt(BaseModel):
    node_id: str = ""
    node_ids: list[str] = Field(default_factory=list)
    rename_applied: bool = False
    all_journeys_valid: bool = False
    repairs_applied: int = 0
    actual_node_id: str = ""
    hints_used: int = 0
    elapsed_seconds: float = 0.0


@router.get("/missions")
async def missions() -> dict[str, Any]:
    return {
        "missions": list_missions(),
        "note": "Missions teach by using the real product. Nothing here simplifies or hides "
        "what the graph actually says.",
    }


@router.post("/projects/{project_id}/missions/{mission_id}/check")
async def check_mission(
    project_id: str, mission_id: str, attempt: MissionAttempt
) -> dict[str, Any]:
    state = get_state()
    live = state.get(project_id)
    if live is None:
        raise NotFoundError(f"No project with id '{project_id}'.")
    mission = MISSION_INDEX.get(mission_id)
    if mission is None:
        raise NotFoundError(f"No mission called '{mission_id}'.")

    result = evaluate(mission_id, live.graph, attempt.model_dump())
    # Hints cost points, but never enough to make a solved mission worth zero.
    score = result.score
    if score and attempt.hints_used:
        score = max(int(mission.points * 0.4), score - attempt.hints_used * 20)

    return {
        "mission_id": mission_id,
        "correct": result.correct,
        "message": result.message,
        "reveal": result.reveal,
        "reveal_labels": result.reveal_labels,
        "score": score,
        "max_score": mission.points,
        "teaches": mission.teaches if result.correct else "",
        "share_text": (
            f"Solved '{mission.title}' in API Galaxy"
            + (f" in {int(attempt.elapsed_seconds)}s" if attempt.elapsed_seconds else "")
            + f" — {score}/{mission.points} points."
            if result.correct
            else ""
        ),
    }
