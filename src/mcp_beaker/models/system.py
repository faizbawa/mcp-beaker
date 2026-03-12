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
    lender: str = ""
    location: str = ""
    vendor: str = ""
    model: str = ""
    serial_number: str = ""
    mac_address: str = ""
    memory: int | None = None
    numa_nodes: int | None = None
    hypervisor: str = ""
    kernel_type: str = ""
    power_type: str = ""
    power_address: str = ""
    lab_controller_id: int | None = None
    release_action: str = ""
    arches: list[str] = Field(default_factory=list)
    lab_controller: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class SystemHistoryEntry(BaseModel):
    """A single activity entry from system history."""

    created: str = ""
    user: str = ""
    service: str = ""
    action: str = ""
    field_name: str = ""
    old_value: str = ""
    new_value: str = ""
