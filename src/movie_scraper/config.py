"""Load and validate config.toml."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TheaterCfg(BaseModel):
    enabled: bool = True
    name: str
    color: str = "#888888"


class Filters(BaseModel):
    title_include: list[str] = Field(default_factory=list)
    title_exclude: list[str] = Field(default_factory=list)
    weekdays: list[str] = Field(default_factory=list)       # e.g. ["Fri","Sat","Sun"]
    earliest: Optional[str] = None                          # "HH:MM" local
    latest: Optional[str] = None                            # "HH:MM" local


class Config(BaseModel):
    timezone: str = "America/Denver"
    days_ahead: int = 14
    output: str = "public/data.json"
    default_runtime_minutes: int = 120
    theaters: dict[str, TheaterCfg]
    filters: Filters = Field(default_factory=Filters)


def load_config(path: str | Path = "config.toml") -> Config:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return Config(**data)
