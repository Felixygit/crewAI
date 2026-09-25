"""CrewAI tools that wrap the deterministic EMA / VWAP stack engine."""

from __future__ import annotations

import json
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ema_vwap_stack.models import MissingInputError
from ema_vwap_stack.rules import build_stack_plan, plan_from_payload, plan_to_yaml_dict
from ema_vwap_stack.sample_data import SAMPLE_SNAPSHOTS, get_snapshot


class PlanFromSampleInput(BaseModel):
    """Build a plan from a named offline sample snapshot."""

    ticker: str = Field(
        default="MU",
        description="Ticker to load from sample snapshots (default MU).",
    )
    tag: str | None = Field(
        default=None,
        description="Optional note substring to disambiguate samples for one ticker.",
    )


class EmaVwapStackPlanTool(BaseTool):
    """Produce the structured EMA / VWAP stack plan for a sample ticker."""

    name: str = "ema_vwap_stack_plan"
    description: str = (
        "Classify regime, score confluence, and emit one structured educational "
        "trade plan (or stand-aside) for a sample ticker using the EMA / VWAP "
        "stack rules. Does not place orders. Returns JSON matching the output schema."
    )
    args_schema: type[BaseModel] = PlanFromSampleInput

    def _run(self, ticker: str = "MU", tag: str | None = None) -> str:
        snap = get_snapshot(ticker, tag)
        if snap is None:
            available = sorted({s.ticker for s in SAMPLE_SNAPSHOTS})
            return json.dumps(
                {
                    "error": f"Unknown sample ticker {ticker!r}",
                    "available_tickers": available,
                }
            )
        plan = build_stack_plan(snap)
        return json.dumps(plan_to_yaml_dict(plan), indent=2)


class ValidateAndPlanInput(BaseModel):
    """Validate a raw market payload and build a plan — refuses missing fields."""

    payload_json: str = Field(
        ...,
        description=(
            "JSON object with required market fields (ticker, session_date, "
            "session_time, timeframe, last, EMAs, VWAP, yesterday H/L, OR H/L, "
            "nasdaq_direction, ...)."
        ),
    )


class ValidateAndPlanTool(BaseTool):
    """Refuse missing required inputs; otherwise emit the structured plan."""

    name: str = "validate_and_plan_stack"
    description: str = (
        "Parse a JSON market snapshot, refuse if required fields are missing "
        "(do not invent values), otherwise run the EMA / VWAP stack pipeline "
        "and return one structured plan object."
    )
    args_schema: type[BaseModel] = ValidateAndPlanInput

    def _run(self, payload_json: str) -> str:
        try:
            payload: dict[str, Any] = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON: {exc}"})
        try:
            plan = plan_from_payload(payload)
        except MissingInputError as exc:
            return json.dumps(
                {
                    "refused": True,
                    "message": str(exc),
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface validation errors cleanly
            return json.dumps({"error": str(exc)})
        return json.dumps(plan_to_yaml_dict(plan), indent=2)
