"""Typed extension point for the user's M3 ramp/blend/calibration recipe.

The original M3 formula is UNSPECIFIED. This module only defines the typed shape a supplied
recipe must take; nothing here provides default values or a substitute formula, and no expression
strings are ever evaluated. M3 stays ``config_required`` until a recipe file validating against
:class:`M3RecipeSpec` is supplied and its execution adapter is implemented (Milestone C).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RampSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_week: int = Field(ge=1, le=52)
    end_week: int = Field(ge=1, le=52)
    multiplier: float = Field(ge=0)


class BlendComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method_id: str
    weight: float = Field(ge=0)


class M3RecipeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe_id: str
    source: str = Field(description="Who supplied the formula and where it is documented.")
    ramp: list[RampSegment]
    blend: list[BlendComponent]
    calibration: Literal["none", "validation_total_ratio"]
    calibration_window: str | None = None
