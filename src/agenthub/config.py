"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Environment
    env: str = "dev"
    port: int = 8080

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Kafka
    kafka_broker: str = "localhost:9092"

    # OpenAI
    openai_api_key: str = "sk-test-key"
    openai_model: str = "gpt-4o-mini"
    openai_price_input: float = 0.00015  # per 1K tokens
    openai_price_output: float = 0.00060  # per 1K tokens

    # Auth & Security
    api_key_signing_secret: str = "change-me-to-strong-secret"

    # Rate Limiting
    rate_limit_qps: int = 5
    rate_limit_burst: int = 10

    # Sessions
    session_ttl_seconds: int = 86400  # 24 hours

    # Observability
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    prometheus_multiproc_dir: str = "/tmp"


settings = Settings()

