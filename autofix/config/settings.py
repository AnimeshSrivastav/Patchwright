from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Model — never hard-code model names outside this file
    model: str = Field(default="gemini-2.0-flash", alias="MODEL")
    router: str = Field(default="llm", alias="ROUTER")

    # Monitoring
    app_log_url: str = Field(alias="APP_LOG_URL")
    poll_interval_s: int = Field(default=10, alias="POLL_INTERVAL_S")

    # GitHub
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    github_repo: str = Field(default="", alias="GITHUB_REPO")

    # Storage
    db_path: str = Field(default="./patchwright.db", alias="DB_PATH")

    # Langfuse / OTel
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")
    otel_endpoint: str = Field(default="http://localhost:4318", alias="OTEL_EXPORTER_OTLP_ENDPOINT")

    # Safety caps (per incident)
    max_iterations: int = Field(default=3, alias="MAX_ITERATIONS")
    max_tokens: int = Field(default=50_000, alias="MAX_TOKENS")
    max_usd: float = Field(default=1.00, alias="MAX_USD")
    max_wall_seconds: int = Field(default=300, alias="MAX_WALL_SECONDS")

    # Routing
    confidence_threshold: float = Field(default=0.6, alias="CONFIDENCE_THRESHOLD")

    # Verifier
    max_diff_lines: int = Field(default=50, alias="MAX_DIFF_LINES")
    max_files_changed: int = Field(default=3, alias="MAX_FILES_CHANGED")

    # Sandbox
    sandbox_cpu_quota: int = Field(default=100_000, alias="SANDBOX_CPU_QUOTA")
    sandbox_mem_limit: str = Field(default="512m", alias="SANDBOX_MEM_LIMIT")
    sandbox_timeout_s: int = Field(default=120, alias="SANDBOX_TIMEOUT_S")

    # Testing / offline mode
    mock_external: bool = Field(default=False, alias="MOCK_EXTERNAL")
