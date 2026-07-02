"""
Configuration and settings for AzurePilot loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings sourced from environment / .env file."""

    # Mode: "demo" (offline mock data) or "live" (real Azure)
    azurepilot_mode: str = Field(default="demo", alias="AZUREPILOT_MODE")

    # Azure Auth
    azure_tenant_id: str = Field(default="", alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(default="", alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(default="", alias="AZURE_CLIENT_SECRET")

    # Azure Scope
    azure_subscription_id: str = Field(default="", alias="AZURE_SUBSCRIPTION_ID")
    azure_resource_group: str = Field(default="", alias="AZURE_RESOURCE_GROUP")

    # LLM — Azure OpenAI
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(default="", alias="AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = Field(default="gpt-4o", alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(
        default="2024-02-15-preview", alias="AZURE_OPENAI_API_VERSION"
    )

    # LLM — OpenAI fallback
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # API Server
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    # Metrics
    metrics_lookback_hours: int = Field(default=24, alias="METRICS_LOOKBACK_HOURS")
    metrics_poll_interval_minutes: int = Field(default=5, alias="METRICS_POLL_INTERVAL_MINUTES")

    model_config = {"env_file": ".env", "populate_by_name": True}

    @property
    def is_demo(self) -> bool:
        return self.azurepilot_mode.lower() == "demo"

    @property
    def llm_provider(self) -> str:
        """Returns 'azure_openai', 'openai', or 'mock'."""
        if self.azure_openai_endpoint and self.azure_openai_api_key:
            return "azure_openai"
        if self.openai_api_key:
            return "openai"
        return "mock"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
