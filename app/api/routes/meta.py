"""Meta endpoint - identifies the running build and current phase.

GET /api/v1/meta -> {
    "name": "DustOps AI",
    "version": "0.0.0",
    "api_version": "v1",
    "current_phase": "B",
    "completed_phases": ["A"]
}
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

import app
from app.api import API_VERSION

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROGRESS_STATE = _REPO_ROOT / ".progress_state.json"


class MetaResponse(BaseModel):
    name: str
    version: str
    api_version: str
    current_phase: str
    completed_phases: list[str]


def _load_phase_state() -> tuple[str, list[str]]:
    if not _PROGRESS_STATE.exists():
        return "A", []
    try:
        data = json.loads(_PROGRESS_STATE.read_text())
    except (json.JSONDecodeError, OSError):
        return "A", []
    current = str(data.get("current_phase", "A"))
    completed_raw = data.get("completed_phases", [])
    completed = [str(p) for p in completed_raw] if isinstance(completed_raw, list) else []
    return current, completed


@router.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    current, completed = _load_phase_state()
    return MetaResponse(
        name="DustOps AI",
        version=app.__version__,
        api_version=API_VERSION,
        current_phase=current,
        completed_phases=completed,
    )
