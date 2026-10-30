import os
import re
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or "").strip()


# ---------------- Zorunlu ayarlar ----------------
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_CHAT_ID = int(_env("TELEGRAM_ADMIN_CHAT_ID", "0") or 0)
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.1-flash-lite")

# ---------------- Sahip / kimlik ayarları ----------------
# Asistanın adına çalıştığı kişi
OWNER_FULL_NAME = _env("OWNER_FULL_NAME", "Ad Soyad")
# Asistanın sizden bahsederken kullandığı hitap (örn. "Ayşe Hanım", "Mehmet Bey")
OWNER_ADDRESS = _env("OWNER_ADDRESS", OWNER_FULL_NAME)
# Hitabın iyelik hali; Türkçe ek kuralları nedeniyle elle yazılır (örn. "Ayşe Hanım'ın", "Mehmet Bey'in")
OWNER_ADDRESS_POSSESSIVE = _env("OWNER_ADDRESS_POSSESSIVE", f"{OWNER_ADDRESS}'in")
# Giden e-postalarda "Kimden" alanında görünen ad
MAIL_FROM_NAME = _env("MAIL_FROM_NAME", OWNER_FULL_NAME)
# İmzada asistanın adı
ASSISTANT_SIGNATURE_NAME = _env("ASSISTANT_SIGNATURE_NAME", f"Gemini ({OWNER_FULL_NAME} Asistanı)")
# İmzanın altına eklenecek web adresi (isteğe bağlı)
SIGNATURE_URL = _env("SIGNATURE_URL")
# Her yanıtta yer alacak şeffaflık notu
TRANSPARENCY_NOTE = _env(
    "TRANSPARENCY_NOTE",
    f"Bu yanıt {OWNER_ADDRESS_POSSESSIVE} kontrolü ve onayı doğrultusunda hazırlanmıştır. "
    f"Sistemdeki her işlem {OWNER_ADDRESS_POSSESSIVE} denetimindedir ve gerekli durumlarda "
    f"kendisi doğrudan iletişime geçecektir."
)

# ---------------- Çalışma ayarları ----------------
DB_PATH = _env("DB_PATH", str(BASE_DIR / "data" / "assistant.db"))
CHECK_INTERVAL = int(_env("CHECK_INTERVAL", "30") or 30)
SERVICE_NAME = _env("SERVICE_NAME", "mailagent.service")

# ---------------- Uygulama kataloğu (isteğe bağlı) ----------------
# Katalog tanımlanırsa: "X uygulamasının linki nedir?" gibi e-postalara otomatik yanıt verilir.
# 1) Basit yöntem: JSON dosyası (bkz. catalog.example.json)
CATALOG_JSON_PATH = _env("CATALOG_JSON_PATH")
# 2) Gelişmiş: uyumlu şemaya sahip bir SQLite veritabanı (salt okunur)
APPS_DB_PATH = _env("APPS_DB_PATH")
# Katalog / vitrin web sitesi (isteğe bağlı)
CATALOG_SITE_URL = _env("CATALOG_SITE_URL", _env("SHOWCASE_BASE_URL"))
SHOWCASE_BASE_URL = CATALOG_SITE_URL  # geriye dönük uyumluluk

# ---------------- Filtreler ----------------
RAW_IGNORED_DOMAINS = _env("IGNORED_DOMAINS", "googlegroups.com,yahoogroups.com,groups.io")
RAW_IGNORED_SENDERS = _env("IGNORED_SENDERS", "noreply,no-reply,donotreply,do-not-reply,mailer-daemon,postmaster")
IGNORED_DOMAINS = [d.strip().lower() for d in RAW_IGNORED_DOMAINS.split(",") if d.strip()]
IGNORED_SENDERS = [s.strip().lower() for s in RAW_IGNORED_SENDERS.split(",") if s.strip()]

# ---------------- Geliştirici ve Hakkında Ayarları ----------------
DEV_NAME = _env("DEV_NAME", "Ömer Göktaş")
DEV_WEBSITE = _env("DEV_WEBSITE", "https://omergoktas.net")
DEV_SHOWCASE = _env("DEV_SHOWCASE", "https://apps.omergoktas.net")
DEV_EMAIL = _env("DEV_EMAIL", "mail@omergoktas.net")


def site_host() -> str:
    """CATALOG_SITE_URL / SIGNATURE_URL için 'https://' olmadan alan adı."""
    url = SIGNATURE_URL or CATALOG_SITE_URL
    return re.sub(r"^https?://", "", url).rstrip("/") if url else ""
