"""Pydantic models for Beaker jobs, recipe sets, recipes, and tasks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TaskResult(BaseModel):
    """A single task within a recipe."""

    model_config = {"coerce_numbers_to_str": True}

    id: str = ""
    name: str = ""
    status: str = ""
    result: str = ""


class RecipeLog(BaseModel):
    """A log file associated with a recipe."""

    href: str = ""
    path: str = ""


class Recipe(BaseModel):
    """A recipe within a recipe set."""

    model_config = {"coerce_numbers_to_str": True}

    id: str = ""
    status: str = ""
    result: str = ""
    whiteboard: str | None = ""
    distro_tree: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] | None = None
    status_reason: str | None = ""
    tasks: list[TaskResult] = Field(default_factory=list)
    logs: list[RecipeLog] = Field(default_factory=list)

    @property
    def system_fqdn(self) -> str:
        if isinstance(self.system, dict):
            return self.system.get("fqdn", "")
        return ""

    @property
    def distro_name(self) -> str:
        if isinstance(self.distro_tree, dict):
            distro = self.distro_tree.get("distro", {})
            if isinstance(distro, dict):
                return distro.get("name", "")
        return ""


class RecipeSet(BaseModel):
    """A recipe set within a job."""

    model_config = {"coerce_numbers_to_str": True}

    id: str = ""
    status: str = ""
    result: str = ""
    priority: str | None = ""
    recipes: list[Recipe] = Field(default_factory=list)


class JobOwner(BaseModel):
    user_name: str = ""


class JobInfo(BaseModel):
    """Detailed information about a Beaker job."""

    model_config = {"coerce_numbers_to_str": True}

    id: str = ""
    status: str = ""
    result: str = ""
    whiteboard: str | None = ""
    is_finished: bool = False
    submitted_time: str | None = ""
    owner: JobOwner | dict[str, Any] | None = None
    recipesets: list[RecipeSet] = Field(default_factory=list)

    @property
    def owner_name(self) -> str:
        if isinstance(self.owner, JobOwner):
            return self.owner.user_name
        if isinstance(self.owner, dict):
            return self.owner.get("user_name", "")
        return ""


class LogFileEntry(BaseModel):
    """A log file returned by taskactions.files()."""

    filename: str = ""
    url: str = ""
    path: str = ""
    server: str = ""
    basepath: str = ""
