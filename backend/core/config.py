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
    # Trailing slashes and stray whitespace around commas are the usual
    # reason an allow-list entry stops matching the browser's exact Origin
    # header, so both are normalized away during parsing.
    CORS_ORIGINS = [
        origin
        for origin in (
            part.strip().rstrip("/") for part in os.environ.get("CORS_ORIGINS", "*").split(",")
        )
        if origin
    ]

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

    def required_cors_origins(self) -> list[str]:
        """Origins the deployed frontend and local dev require, merged with
        the parsed CORS_ORIGINS env value. Duplicates removed, order kept."""
        required = [
            "https://thermointel-7qm6.onrender.com",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        merged = required + [o for o in self.CORS_ORIGINS if o not in required]
        # "*" would be dropped by Starlette when allow_credentials=True
        # (starlette/http.py rejects the header combination), so keep the
        # allow-list explicit.
        return [o for o in merged if o != "*"]


settings = Settings()
