"""Runtime configuration.

Everything is overridable by environment variable (prefix ``API_GALAXY_``) so the app can
be configured without editing files, and every default is chosen so that a fresh clone
works offline with no setup.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    override = os.environ.get("API_GALAXY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser() / "api-galaxy"
    return Path.home() / ".api-galaxy"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="API_GALAXY_", env_file=".env", extra="ignore", case_sensitive=False
    )

    # --- server ---------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8099
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000",
                                                            "http://127.0.0.1:3000"])
    log_level: str = "info"

    # --- storage --------------------------------------------------------------
    data_dir: Path = Field(default_factory=default_data_dir)

    # --- providers ------------------------------------------------------------
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout: float = 180.0

    external_providers_enabled: bool = Field(
        default=True,
        description="Master switch. When false, no request can leave this machine.",
    )
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k2-0905-preview"
    kimi_api_key: str = ""
    kimi_timeout: float = 120.0

    # --- limits ---------------------------------------------------------------
    max_upload_bytes: int = 12 * 1024 * 1024
    max_projects: int = 50
    allow_remote_refs: bool = False
    allow_private_network_urls: bool = Field(
        default=False,
        description="SSRF guard for 'import from URL'. Off by default and stays off unless "
        "the user explicitly turns it on.",
    )
    request_rate_limit_per_minute: int = 120

    # --- demo -----------------------------------------------------------------
    samples_dir: Path | None = None

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "api-galaxy.sqlite"

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path}"

    def resolve_samples_dir(self) -> Path:
        if self.samples_dir is not None:
            return Path(self.samples_dir)
        # apps/api/api_galaxy/app/settings.py → repo root is four parents up.
        return Path(__file__).resolve().parents[4] / "samples"

    def ensure_dirs(self) -> None:
        for directory in (self.data_dir, self.projects_dir, self.exports_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
