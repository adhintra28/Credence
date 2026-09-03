"""Typed, validated configuration loader via Pydantic Settings.

One config, ``config.yaml``, loaded through this single module.
No literal thresholds, dates, or paths anywhere else.

Usage::

    from src.config import get_settings
    cfg = get_settings()          # cached singleton
    cfg = get_settings("other.yaml")  # explicit path
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator


# ── Sub-models ────────────────────────────────────────────────────────
class DataConfig(BaseModel):
    n_customers: int = Field(ge=10, description="Number of synthetic customers")
    start_date: str
    months: int = Field(ge=1)
    emi_day: int = Field(ge=1, le=28)
    positive_rate_target: float = Field(ge=0.01, le=0.30)
    cure_rate: float = Field(default=0.15, ge=0.0, le=1.0, description="Share of stressed customers that cure")


class ScoringConfig(BaseModel):
    scoring_date: str
    train_months: str  # e.g. "1-8"
    valid_months: str
    test_months: str
    windows: list[int] = [7, 14, 28]


class TierConfig(BaseModel):
    amber_min: float = Field(ge=0.0, le=1.0)
    green_max: float = Field(ge=0.0, le=1.0)
    red_min: float = Field(ge=0.0, le=1.0)
    red_cap_per_day: int = Field(ge=1)
    suppression_days: int = Field(ge=1)


class PathsConfig(BaseModel):
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    models_dir: str = "models"
    outputs_dir: str = "data/outputs"


class ModelConfig(BaseModel):
    champion: str = "lightgbm"
    challenger: str = "xgboost"
    calibrate: bool = True


class DatabaseConfig(BaseModel):
    url: str = Field(
        default="postgresql+psycopg2://predelinq:predelinq@localhost:5432/predelinq",
        description="SQLAlchemy database URL",
    )
    pool_size: int = 5
    echo: bool = False


class AuthConfig(BaseModel):
    secret_key: str = Field(default="CHANGE-ME-IN-PRODUCTION-NOT-DEFAULT")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_minutes: int = 1440


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5000"])
    debug: bool = False


# ── Root model ────────────────────────────────────────────────────────
class Settings(BaseModel):
    """Complete application configuration.  Loaded from ``config.yaml``."""

    seed: int = 42
    data: DataConfig
    scoring: ScoringConfig
    tiers: TierConfig
    paths: PathsConfig = PathsConfig()
    model: ModelConfig = ModelConfig()
    database: DatabaseConfig = DatabaseConfig()
    auth: AuthConfig = AuthConfig()
    server: ServerConfig = ServerConfig()

    model_config = {"extra": "forbid"}  # unknown keys raise

    @model_validator(mode="after")
    def _check_tier_order(self) -> "Settings":
        if self.tiers.amber_min >= self.tiers.red_min:
            raise ValueError(f"amber_min ({self.tiers.amber_min}) must be < red_min ({self.tiers.red_min})")
        return self


def _load_yaml(path: str | Path) -> dict:
    """Read a YAML file and return the raw dict."""
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise TypeError(f"Expected dict from {path}, got {type(raw).__name__}")
    return raw


@lru_cache(maxsize=4)
def get_settings(config_path: str | None = None) -> Settings:
    """Return a validated, cached :class:`Settings` instance.

    Parameters
    ----------
    config_path:
        Explicit path.  Falls back to ``$PREDELINQ_CONFIG`` then ``config.yaml``.

    Raises
    ------
    ValidationError   – on unknown or missing keys (global rule #1).
    FileNotFoundError – when the config file does not exist.
    """
    path = config_path or os.environ.get("PREDELINQ_CONFIG", "config.yaml")
    raw = _load_yaml(path)
    return Settings(**raw)


def get_settings_uncached(config_path: str | None = None) -> Settings:
    """Same as :func:`get_settings` but bypasses the LRU cache."""
    path = config_path or os.environ.get("PREDELINQ_CONFIG", "config.yaml")
    raw = _load_yaml(path)
    return Settings(**raw)
