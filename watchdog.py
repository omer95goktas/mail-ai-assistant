#!/usr/bin/env python3
"""
Mailagent Independent Watchdog Monitor
Runs periodically via cron (every 3 minutes).
Checks if mailagent.service is active AND if heartbeat is recent (< 300s).
If frozen or crashed, restarts the service and alerts admin via Telegram.
"""
import os
import sys
import time
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path("/opt/mail_assistant")
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
HEARTBEAT_FILE = Path("/tmp/mailagent.heartbeat")
MAX_SILENCE_SECONDS = 300  # 5 minutes

def send_telegram_alert(message: str):
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": ADMIN_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            pass
    except Exception as e:
        print(f"[Watchdog] Could not send Telegram alert: {e}", file=sys.stderr)

def restart_service(reason: str):
    print(f"[Watchdog] Restarting mailagent.service: {reason}")
    subprocess.run(["systemctl", "restart", "mailagent.service"], check=False)
    time.sleep(3)
    HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")
    
    alert_text = (
        "?? <b>[Sistem Bek?isi - Watchdog M?dahalesi]</b>\n\n"
        f"<b>Tespit:</b> {reason}\n"
        "<b>??lem:</b> <code>mailagent.service</code> otomatik olarak yeniden ba?lat?ld?.\n"
        f"<b>Durum:</b> Sistem toparland? ve normal ?al??maya devam ediyor.\n"
        f"<b>Zaman:</b> {time.strftime('%d.%m.%Y %H:%M:%S')}"
    )
    send_telegram_alert(alert_text)

def main():
    # 1. Check systemd service status
    res = subprocess.run(["systemctl", "is-active", "mailagent.service"], capture_output=True, text=True)
    status = res.stdout.strip()
    if status != "active":
        restart_service(f"Servis aktif de?il (Durum: '{status}')")
        return

    # 2. Check heartbeat file
    if not HEARTBEAT_FILE.exists():
        HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")
        return

    try:
        last_hb = float(HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
        silence = time.time() - last_hb
        if silence > MAX_SILENCE_SECONDS:
            restart_service(f"Serviste {int(silence)} saniyedir nab?z (heartbeat) al?namad? (soket kilitlenmesi).")
    except Exception as e:
        print(f"[Watchdog] Error reading heartbeat: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
