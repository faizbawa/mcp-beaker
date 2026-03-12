"""Pydantic models for Beaker distros and distro trees."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DistroTreeInfo(BaseModel):
    """A distro tree returned by distrotrees.filter()."""

    distro_name: str = ""
    distro_id: int | None = None
    distro_tree_id: int | None = None
    arch: str = ""
    variant: str = ""
    distro_tags: list[str] = Field(default_factory=list)
    available: list[Any] = Field(default_factory=list)
