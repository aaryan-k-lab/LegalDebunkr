import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # Document Intelligence
    di_endpoint: str = _env("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    di_key: str = _env("AZURE_DOCUMENT_INTELLIGENCE_KEY")

    # Content Understanding
    cu_endpoint: str = _env("AZURE_CONTENT_UNDERSTANDING_ENDPOINT")
    cu_key: str = _env("AZURE_CONTENT_UNDERSTANDING_KEY")
    cu_api_version: str = _env("AZURE_CONTENT_UNDERSTANDING_API_VERSION", "2025-05-01-preview")
    cu_analyzer_id: str = _env("AZURE_CONTENT_UNDERSTANDING_ANALYZER_ID", "legaldebunkr-analyzer")
    cu_base_analyzer_id: str = _env("AZURE_CONTENT_UNDERSTANDING_BASE_ANALYZER_ID")
    cu_completion_model: str = _env("AZURE_CONTENT_UNDERSTANDING_COMPLETION_MODEL")

    # Azure OpenAI (language generation)
    aoai_endpoint: str = _env("AZURE_OPENAI_ENDPOINT")
    aoai_key: str = _env("AZURE_OPENAI_KEY")
    aoai_api_version: str = _env("AZURE_OPENAI_API_VERSION", "2024-10-21")
    aoai_deployment: str = _env("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    # App
    max_upload_mb: int = int(_env("MAX_UPLOAD_MB", "15"))
    max_sections: int = int(_env("MAX_SECTIONS", "40"))
    debug: bool = _env("FLASK_DEBUG", "0") == "1"

    # Abuse / cost protection
    rate_limit_analyze: str = _env("RATE_LIMIT_ANALYZE", "5 per minute;30 per day")
    rate_limit_ask: str = _env("RATE_LIMIT_ASK", "20 per minute;200 per day")
    rate_limit_default: str = _env("RATE_LIMIT_DEFAULT", "120 per minute")
    # memory:// is per-process. Use redis://host:6379 when running several workers/instances.
    ratelimit_storage_uri: str = _env("RATELIMIT_STORAGE_URI", "memory://")
    max_concurrent_analyses: int = int(_env("MAX_CONCURRENT_ANALYSES", "4"))
    trust_proxy_hops: int = int(_env("TRUST_PROXY_HOPS", "0"))
    store_ttl_seconds: int = int(_env("STORE_TTL_SECONDS", "3600"))
    store_max_items: int = int(_env("STORE_MAX_ITEMS", "200"))

    @property
    def di_ready(self) -> bool:
        return bool(self.di_endpoint and self.di_key)

    @property
    def cu_ready(self) -> bool:
        return bool(self.cu_endpoint and self.cu_key)

    @property
    def llm_ready(self) -> bool:
        return bool(self.aoai_endpoint and self.aoai_key)


settings = Settings()
