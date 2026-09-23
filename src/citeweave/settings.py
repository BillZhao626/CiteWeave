"""Environment configuration. Secret representations never contain credential values."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CW_", env_file=ROOT / ".env", extra="ignore")
    database_url: SecretStr = SecretStr("")
    db_password: SecretStr = SecretStr("")
    admin_token: SecretStr = SecretStr("")
    broker_url: str = "redis://127.0.0.1:16379/0"
    qdrant_url: str = "http://127.0.0.1:16333"
    model_url: str = "http://127.0.0.1:18081"
    model_token: SecretStr = SecretStr("")
    blob_root: Path = ROOT / ".runtime/blobs"
    web_root: Path = ROOT / "apps/web/dist"
    workspace_id: UUID = uuid5(NAMESPACE_URL, "citeweave-personal-workspace")
    deepseek_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="DEEPSEEK_API_KEY")
    deepseek_model: Literal["deepseek-flash"] = "deepseek-flash"
    telecom_answer_prompt: Literal["answer-telecom-v1", "answer-telecom-consistency-v1"] = "answer-telecom-v1"
    lease_seconds: int = Field(default=30, ge=5, le=300)
    max_attempts: int = Field(default=3, ge=1, le=5)
    monthly_budget_yuan: float = Field(default=50, gt=0, le=50)
    query_deadline_seconds: int = Field(default=60, ge=10, le=120)
    max_active_queries: int = Field(default=1, ge=1, le=8)
    ingestion_deadline_seconds: int = Field(default=900, ge=30, le=7200)
    provider_attempts: int = Field(default=2, ge=1, le=3)
    model_attempts: int = Field(default=2, ge=1, le=3)
    retry_backoff_seconds: float = Field(default=0.5, ge=0, le=3)
    breaker_threshold: int = Field(default=3, ge=2, le=10)
    breaker_cooldown_seconds: int = Field(default=20, ge=1, le=120)
    fault_root: Path | None = None
    enable_faults: bool = False

    def db_url(self):
        from sqlalchemy import URL

        explicit = self.database_url.get_secret_value()
        if explicit:
            return explicit.replace("postgresql://", "postgresql+psycopg://", 1)
        return URL.create(
            "postgresql+psycopg",
            username="citeweave",
            password=self.db_password.get_secret_value(),
            host="127.0.0.1",
            port=15432,
            database="citeweave",
        )

    def gateway_token(self):
        import hashlib

        return (
            self.model_token.get_secret_value()
            or hashlib.sha256(("model-gateway:" + self.admin_token.get_secret_value()).encode()).hexdigest()
        )


@lru_cache
def settings():
    return Settings()
