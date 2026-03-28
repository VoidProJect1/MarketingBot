"""
config.py — Bot Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Bot Settings ─────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set in .env file!")

# Comma-separated admin user IDs. If empty, ALL users can access the bot.
_raw_admins = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [int(x.strip()) for x in _raw_admins.split(",") if x.strip().isdigit()]

# ─── Paths ────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
SESSIONS_DIR = BASE_DIR / "sessions"

DATA_DIR.mkdir(exist_ok=True)
SESSIONS_DIR.mkdir(exist_ok=True)

DB_FILE = DATA_DIR / "db.json"

# ─── Defaults ─────────────────────────────────
DEFAULT_DELAY: int = 30          # seconds between messages to each group
MIN_DELAY:     int = 5           # hard minimum delay allowed
LOG_LEVEL:     str = os.getenv("LOG_LEVEL", "INFO")
