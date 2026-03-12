"""Pydantic models for Beaker systems."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SystemListItem(BaseModel):
    """A system entry from a Beaker Atom feed listing."""

    fqdn: str = ""
    url: str = ""


class SystemOwner(BaseModel):
    user_name: str = ""
    email_address: str = ""


class SystemInfo(BaseModel):
    """Detailed information about a single Beaker system."""

    fqdn: str = ""
    status: str = ""
    system_type: str = Field("", alias="type")
    owner: SystemOwner | None = None
    user: SystemOwner | None = None
    lender: str | None = ""
    location: str | None = ""
    vendor: str | None = ""
    model: str | None = ""
    serial_number: str | None = ""
    mac_address: str | None = ""
    memory: int | None = None
    numa_nodes: int | None = None
    hypervisor: str | None = ""
    kernel_type: str | None = ""
    power_type: str | None = ""
    power_address: str | None = ""
    lab_controller_id: int | None = None
    release_action: str | None = ""
    arches: list[str] = Field(default_factory=list)
    lab_controller: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class SystemHistoryEntry(BaseModel):
    """A single activity entry from system history."""

    created: str = ""
    user: str | None = ""
    service: str = ""
    action: str = ""
    field_name: str = ""
    old_value: str | None = ""
    new_value: str | None = ""
