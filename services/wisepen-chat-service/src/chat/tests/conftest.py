from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


# BootstrapSettings reads environment variables during module import. Load the
# service .env without changing pytest's configured project root.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
