import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_CHAT_ID = int(os.getenv("TELEGRAM_ADMIN_CHAT_ID", "0"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "assistant.db")).strip()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

# Showcase app catalog integration
APPS_DB_PATH = os.getenv("APPS_DB_PATH", "/var/www/apps.omergoktas.net/data/apps.sqlite").strip()
SHOWCASE_BASE_URL = os.getenv("SHOWCASE_BASE_URL", "https://apps.omergoktas.net").strip()

# Mailing list & Bulk mail ignore filters
RAW_IGNORED_DOMAINS = os.getenv("IGNORED_DOMAINS", "googlegroups.com,yahoogroups.com")
RAW_IGNORED_SENDERS = os.getenv("IGNORED_SENDERS", "noreply,no-reply,donotreply,do-not-reply,mailer-daemon,postmaster")

IGNORED_DOMAINS = [d.strip().lower() for d in RAW_IGNORED_DOMAINS.split(",") if d.strip()]
IGNORED_SENDERS = [s.strip().lower() for s in RAW_IGNORED_SENDERS.split(",") if s.strip()]