"""Application configuration. All values come from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    """Runtime configuration for the ThermoIntel backend."""

    APP_NAME = "ThermoIntel API"
    APP_VERSION = "2.0.0-phase2"

    # --- Database (MongoDB Atlas compatible) ---
    MONGO_URL = os.environ["MONGO_URL"]
    DB_NAME = os.environ["DB_NAME"]

    # --- HTTP ---
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

    # --- Operational scope ---
    OPERATIONAL_COUNTRY = "India"

    # --- Phase 3 / 4 / 5 placeholders (intentionally unset in Phase 2) ---
    FIRMS_API_KEY = os.environ.get("FIRMS_API_KEY") or None
    FIRMS_BASE_URL = os.environ.get("FIRMS_BASE_URL") or None
    ACTIVE_MODEL_VERSION = os.environ.get("ACTIVE_MODEL_VERSION") or None

    # --- Development / demo data ---
    # Demo data is always tagged data_origin="demo" and is never returned
    # unless a request explicitly asks for it.
    ALLOW_DEMO_DATA = os.environ.get("ALLOW_DEMO_DATA", "true").lower() == "true"

    @property
    def firms_configured(self) -> bool:
        return bool(self.FIRMS_API_KEY and self.FIRMS_BASE_URL)


settings = Settings()
