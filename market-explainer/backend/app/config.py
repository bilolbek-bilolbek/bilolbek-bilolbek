import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "").strip()
    data_mode: str = os.getenv("DATA_MODE", "auto").strip().lower()
    cache_ttl: float = float(os.getenv("CACHE_TTL_SECONDS", "60"))
    timeout: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "6"))


settings = Settings()
