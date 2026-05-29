"""
Configuration management for GitMoji AI
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file"""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Limits (Free vs Pro)
    free_commits_per_month: int = 50
    free_changelog_per_month: int = 3

    # Pro activation
    pro_license_key: str = ""
    pro_api_url: str = ""

    # StarsPay integration (optional REST API fallback)
    starspay_api_url: str = ""
    starspay_api_key: str = ""

    # Git defaults
    default_language: str = "en"  # en, ru, es, de, fr, ja, zh
    commit_style: str = "conventional"  # conventional, emoji, plain
    changelog_format: str = "keepachangelog"  # keepachangelog, angular, custom

    # Paths
    config_dir: Path = Path.home() / ".gitmoji-ai"

    model_config = {"env_prefix": "GMAI_", "env_file": ".env", "extra": "ignore"}

    @property
    def is_pro(self) -> bool:
        """Check if Pro license key is set. Actual verification done in usage.py"""
        return bool(self.pro_license_key)

    @property
    def db_path(self) -> Path:
        return self.config_dir / "usage.db"

    def ensure_config_dir(self):
        """Create config directory if not exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)


_settings_instance = None

def get_settings() -> Settings:
    """Get cached settings instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
