"""Runtime settings, loaded from environment / .env.

No secret ever appears in code or in git. Every key is optional: a missing key
disables its provider, it never crashes the application and never causes a
fake value to be substituted.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- mode -------------------------------------------------------------
    mock_mode: bool = Field(default=False)
    log_level: str = "INFO"
    env: str = "local"

    # --- storage ----------------------------------------------------------
    database_url: str = "sqlite:///data/crypto_intel.db"

    # --- api --------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8100
    cors_origins: str = "http://localhost:5273,http://127.0.0.1:5273"
    # Actif par defaut: sans lui, rien ne rafraichit les series et la page
    # affiche des percentiles corrects calcules sur des observations vieilles
    # d'un jour. Mettre SCHEDULER_ENABLED=false pour une commande ponctuelle.
    scheduler_enabled: bool = True

    # --- llm --------------------------------------------------------------
    llm_provider: str = "none"
    llm_model: str = "claude-opus-5"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4000
    llm_timeout: int = 120

    # --- free keys --------------------------------------------------------
    fred_api_key: str = ""
    congress_api_key: str = ""
    etherscan_api_key: str = ""
    sec_user_agent: str = "CryptoIntelligence/0.1 (personal research)"

    # --- paid keys (all optional) ----------------------------------------
    glassnode_api_key: str = ""
    cryptoquant_api_key: str = ""
    nansen_api_key: str = ""
    arkham_api_key: str = ""
    coinglass_api_key: str = ""
    sosovalue_api_key: str = ""

    # --- rpc --------------------------------------------------------------
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"
    eth_rpc_url: str = ""

    # --- http -------------------------------------------------------------
    http_timeout: int = 20
    http_user_agent: str = "CryptoIntelligence/0.1 (personal research tool)"
    cache_enabled: bool = True

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    # --- derived paths ----------------------------------------------------
    @property
    def root(self) -> Path:
        return PROJECT_ROOT

    @property
    def config_dir(self) -> Path:
        return PROJECT_ROOT / "config"

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def cache_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "cache"

    @property
    def fixtures_dir(self) -> Path:
        return PROJECT_ROOT / "fixtures"

    @property
    def knowledge_dir(self) -> Path:
        return PROJECT_ROOT / "knowledge"

    @property
    def etf_import_dir(self) -> Path:
        return PROJECT_ROOT / "data" / "imports" / "etf"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_database_url(self) -> str:
        """Make a relative sqlite path absolute so the CLI and the API always
        open the same file regardless of the working directory."""
        url = self.database_url
        prefix = "sqlite:///"
        if url.startswith(prefix):
            raw = url[len(prefix) :]
            p = Path(raw)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            p.parent.mkdir(parents=True, exist_ok=True)
            return f"{prefix}{p}"
        return url

    def api_key_for(self, name: str) -> str:
        """Look up an API key by its provider-config name (e.g. 'FRED_API_KEY')."""
        return str(getattr(self, name.lower(), "") or "")

    def has_key(self, name: str) -> bool:
        return bool(self.api_key_for(name).strip())

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider in ("", "none"):
            return False
        # Ollama and mock run locally, no key needed.
        if self.llm_provider in ("ollama", "mock"):
            return True
        return bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    """Used by tests that patch the environment."""
    get_settings.cache_clear()
    return get_settings()
