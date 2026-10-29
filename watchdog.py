#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mailagent Independent Watchdog Monitor (cron, every 3 minutes)

1. mailagent.service aktif mi?            -> değilse yeniden başlat + bildir
2. Heartbeat (arka plan döngüsü) taze mi? -> 5 dk sessizse yeniden başlat + bildir
3. Restart fırtınası koruması             -> 1 saatte 4'ten fazla müdahale olursa durup yöneticiyi uyar
4. Günlük SQLite yedeği (son 7 gün)       -> data/backups/
5. Disk doluluk uyarısı (%90 üstü)
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path("/opt/mail_assistant")
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "assistant.db")))
HEARTBEAT_FILE = Path("/tmp/mailagent.heartbeat")
STATE_FILE = BASE_DIR / "data" / "watchdog_state.json"
BACKUP_DIR = BASE_DIR / "data" / "backups"
MAX_SILENCE_SECONDS = 300
MAX_RESTARTS_PER_HOUR = 4
SERVICE = "mailagent.service"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"restarts": [], "last_backup": 0, "storm_alerted": 0, "disk_alerted": 0}


def save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    except Exception as e:
        print(f"[Watchdog] state save error: {e}", file=sys.stderr)


def send_telegram_alert(message: str):
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15):
            pass
    except Exception as e:
        print(f"[Watchdog] Telegram alert failed: {e}", file=sys.stderr)


def service_status() -> str:
    res = subprocess.run(["systemctl", "is-active", SERVICE], capture_output=True, text=True)
    return res.stdout.strip()


def restart_service(reason: str, state: dict):
    now = time.time()
    state["restarts"] = [t for t in state.get("restarts", []) if now - t < 3600]

    if len(state["restarts"]) >= MAX_RESTARTS_PER_HOUR:
        # Restart storm: something is structurally wrong (bad password, code error, etc.)
        if now - state.get("storm_alerted", 0) > 3600:
            state["storm_alerted"] = now
            send_telegram_alert(
                "🚨 <b>[Watchdog] Tekrarlayan arıza tespit edildi</b>\n\n"
                f"Son 1 saatte {len(state['restarts'])} kez yeniden başlatma yapıldı.\n"
                f"<b>Son tespit:</b> {reason}\n"
                "Sistem yine de denemeye devam ediyor; kalıcı bir sorun olabilir, kontrol önerilir."
            )
        # still try (systemd may have given up), but don't spam
        subprocess.run(["systemctl", "reset-failed", SERVICE], check=False)
        subprocess.run(["systemctl", "restart", SERVICE], check=False)
        state["restarts"].append(now)
        return

    print(f"[Watchdog] Restarting {SERVICE}: {reason}")
    subprocess.run(["systemctl", "reset-failed", SERVICE], check=False)
    subprocess.run(["systemctl", "restart", SERVICE], check=False)
    state["restarts"].append(now)
    time.sleep(8)
    HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")

    ok = service_status() == "active"
    send_telegram_alert(
        "🛡️ <b>[Sistem Bekçisi - Otomatik Müdahale]</b>\n\n"
        f"<b>Tespit:</b> {reason}\n"
        f"<b>İşlem:</b> <code>{SERVICE}</code> otomatik olarak yeniden başlatıldı.\n"
        f"<b>Sonuç:</b> {'✅ Servis tekrar çalışıyor.' if ok else '❌ Servis başlatılamadı, kontrol gerekiyor.'}\n"
        f"<b>Zaman:</b> {time.strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        "<i>Okunmamış e-postalar kalıcı kuyrukta tutulduğu için kayıp yaşanmaz.</i>"
    )


def daily_backup(state: dict):
    now = time.time()
    if now - state.get("last_backup", 0) < 86400 or not DB_PATH.exists():
        return
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = BACKUP_DIR / f"assistant_{time.strftime('%Y%m%d')}.db"
        src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
        dst = sqlite3.connect(str(target))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        backups = sorted(BACKUP_DIR.glob("assistant_*.db"))
        for old in backups[:-7]:
            old.unlink(missing_ok=True)
        state["last_backup"] = now
        print(f"[Watchdog] Backup written: {target}")
    except Exception as e:
        print(f"[Watchdog] Backup failed: {e}", file=sys.stderr)


def disk_check(state: dict):
    try:
        usage = shutil.disk_usage("/")
        pct = usage.used / usage.total * 100
        if pct > 90 and time.time() - state.get("disk_alerted", 0) > 6 * 3600:
            state["disk_alerted"] = time.time()
            send_telegram_alert(f"💾 <b>[Watchdog] Disk doluluğu kritik:</b> %{pct:.0f}. Veritabanı yazımı risk altında.")
    except Exception:
        pass


def main():
    state = load_state()
    try:
        status = service_status()
        if status != "active":
            restart_service(f"Servis aktif değil (durum: '{status}')", state)
            return

        if not HEARTBEAT_FILE.exists():
            HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")
        else:
            try:
                silence = time.time() - float(HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                silence = 0
                HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")
            if silence > MAX_SILENCE_SECONDS:
                restart_service(f"Arka plan döngüsünden {int(silence)} saniyedir nabız alınamadı (donma).", state)
                return

        daily_backup(state)
        disk_check(state)
    finally:
        save_state(state)


if __name__ == "__main__":
    main()
