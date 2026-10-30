#!/usr/bin/env bash
# =====================================================================
#  Yapay Zekâ E-posta Asistanı — Kurulum Betiği
#  Kullanım (proje klasörünün içindeyken):   sudo bash install.sh
#  Betik tekrar tekrar çalıştırılabilir; mevcut ayarlarınızı bozmaz.
# =====================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }

if [[ $EUID -ne 0 ]]; then
  red "Bu betik yönetici (root) yetkisiyle çalışmalı. Şöyle çalıştırın:  sudo bash install.sh"
  exit 1
fi

echo "== 1/6 Python kontrol ediliyor =="
if ! command -v python3 >/dev/null 2>&1; then
  yellow "Python 3 bulunamadı, kuruluyor..."
  apt-get update -y && apt-get install -y python3 python3-venv python3-pip
fi
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  red "Python $PYV bulundu; en az Python 3.10 gerekiyor."
  exit 1
fi
if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update -y && apt-get install -y python3-venv
fi
green "Python $PYV hazır."

echo "== 2/6 Sanal ortam ve paketler =="
if [[ ! -d venv ]]; then
  python3 -m venv venv || { apt-get install -y python3-venv && python3 -m venv venv; }
fi
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q
green "Paketler kuruldu."

echo "== 3/6 Ayar dosyası (.env) =="
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  yellow "Yeni bir .env dosyası oluşturuldu: $APP_DIR/.env"
  yellow "Lütfen şimdi bu dosyayı açıp bilgilerinizi girin, ardından betiği tekrar çalıştırın:"
  echo "    nano $APP_DIR/.env"
  echo "    sudo bash install.sh"
  exit 0
fi
chmod 600 .env

if ! ./venv/bin/python3 - <<'EOF'
import sys
from dotenv import dotenv_values
v = dotenv_values(".env")
problems = []
tok = (v.get("TELEGRAM_BOT_TOKEN") or "").strip()
if not tok or tok.startswith("123456789:ABC"):
    problems.append("TELEGRAM_BOT_TOKEN doldurulmamış")
cid = (v.get("TELEGRAM_ADMIN_CHAT_ID") or "").strip()
if not cid.lstrip("-").isdigit() or cid == "123456789":
    problems.append("TELEGRAM_ADMIN_CHAT_ID doldurulmamış (yalnızca rakam olmalı)")
key = (v.get("GEMINI_API_KEY") or "").strip()
if not key or key.startswith("BURAYA"):
    problems.append("GEMINI_API_KEY doldurulmamış")
if (v.get("OWNER_FULL_NAME") or "").strip() in ("", "Ayşe Yılmaz", "Ad Soyad"):
    problems.append("OWNER_FULL_NAME ve diğer kimlik ayarları örnek değerde (kendi bilgilerinizi yazın)")
if problems:
    print("\n".join(" - " + p for p in problems))
    sys.exit(1)
EOF
then
  red ".env dosyasında eksikler var (yukarıda listelendi). Düzeltip betiği tekrar çalıştırın:"
  echo "    nano $APP_DIR/.env"
  exit 1
fi
green ".env ayarları geçerli görünüyor."

SERVICE_NAME=$(./venv/bin/python3 -c 'from dotenv import dotenv_values; print((dotenv_values(".env").get("SERVICE_NAME") or "mailagent.service").strip())')
mkdir -p data

echo "== 4/6 Ön test (Telegram ve Gemini bağlantısı) =="
if ! ./venv/bin/python3 - <<'EOF'
import asyncio, config
from telegram import Bot
async def t():
    me = await Bot(config.TELEGRAM_BOT_TOKEN).get_me()
    print(f"   Telegram botu: @{me.username}")
asyncio.run(t())
from google import genai
c = genai.Client(api_key=config.GEMINI_API_KEY)
r = c.models.generate_content(model=config.GEMINI_MODEL, contents="Sadece 'tamam' yaz.")
print(f"   Gemini ({config.GEMINI_MODEL}): {(r.text or '').strip()[:20]}")
EOF
then
  red "Ön test başarısız (yukarıdaki hataya bakın). TELEGRAM_BOT_TOKEN, GEMINI_API_KEY ve GEMINI_MODEL değerlerini kontrol edin."
  exit 1
fi
green "Bağlantılar çalışıyor."

echo "== 5/6 Sistem servisi ($SERVICE_NAME) =="
sed "s#__APP_DIR__#$APP_DIR#g" mailagent.service > "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"
sleep 8
if [[ "$(systemctl is-active "$SERVICE_NAME")" == "active" ]]; then
  green "Servis çalışıyor."
else
  red "Servis başlatılamadı. Hata kayıtları için:  journalctl -u $SERVICE_NAME -n 50"
  exit 1
fi

echo "== 6/6 Bekçi (watchdog) zamanlaması =="
CRON_LINE="*/3 * * * * $APP_DIR/venv/bin/python3 $APP_DIR/watchdog.py > /dev/null 2>&1"
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -v "$APP_DIR/watchdog.py" || true)
printf "%s\n%s\n" "$EXISTING_CRON" "$CRON_LINE" | sed '/^$/d' | crontab -
green "Bekçi her 3 dakikada bir servisi kontrol edecek."

echo
green "KURULUM TAMAMLANDI!"
echo "Şimdi Telegram'da botunuza /start yazın, ardından /hesap_ekle ile e-posta hesabınızı ekleyin."
echo "Durum:   systemctl status $SERVICE_NAME"
echo "Kayıtlar: journalctl -u $SERVICE_NAME -f"
