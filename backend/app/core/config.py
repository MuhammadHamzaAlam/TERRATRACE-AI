"""Application settings, loaded from environment variables / .env (never from code)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(REPO_ROOT / ".env")), extra="ignore")

    app_name: str = "TerraTrace AI"
    environment: str = "development"
    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'terratrace.db'}"
    storage_dir: Path = REPO_ROOT / "data" / "storage"
    models_dir: Path = REPO_ROOT / "models"
    reports_dir: Path = REPO_ROOT / "reports"
    levir_root: Path = REPO_ROOT / "data" / "raw" / "LEVIR-CD"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_mb: int = 200
    rate_limit_per_minute: int = 240
    # Inference
    tile_size: int = 256
    tile_overlap: int = 32
    prob_threshold: float = 0.5
    min_event_pixels: int = 20
    # LLM
    llm_provider: str = "ollama"  # ollama | grok
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = ""
    llm_timeout_s: float = 120.0
    llm_max_tool_rounds: int = 5
    # Copernicus Data Space
    cdse_username: str = ""
    cdse_password: str = ""
    cdse_client_id: str = "cdse-public"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for p in (s.storage_dir, s.models_dir, s.reports_dir):
        Path(p).mkdir(parents=True, exist_ok=True)
    if s.database_url.startswith("sqlite:///"):
        Path(s.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    return s
