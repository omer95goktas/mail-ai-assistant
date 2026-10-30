import asyncio
import logging
import logging.handlers
import sys
from telegram.constants import ParseMode
from telegram.ext import Application

import config
import database
import group_assistant
from telegram import BotCommand
from bot import setup_bot_handlers, check_emails_cycle
import time
from pathlib import Path

HEARTBEAT_FILE = Path("/tmp/mailagent.heartbeat")

def update_heartbeat():
    try:
        HEARTBEAT_FILE.write_text(str(time.time()), encoding="utf-8")
    except Exception as e:
        pass

# Setup logging with RotatingFileHandler to avoid unbounded disk usage
file_handler = logging.handlers.RotatingFileHandler(
    config.BASE_DIR / "assistant.log",
    maxBytes=5 * 1024 * 1024,  # 5 MB per file
    backupCount=3,
    encoding="utf-8"
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        file_handler
    ]
)
logger = logging.getLogger("mailagent")

async def background_loop(app: Application):
    logger.info(f"Background email check loop running every {config.CHECK_INTERVAL} seconds.")
    await asyncio.sleep(3)
    while True:
        try:
            # Each step has its own timeout; this is only a last-resort guard.
            # Interruption is safe: unprocessed mails stay in the durable queue.
            await asyncio.wait_for(check_emails_cycle(app.bot), timeout=300.0)
        except asyncio.TimeoutError:
            logger.warning("Email cycle exceeded 300s; queue preserved, continuing next tick.")
        except asyncio.CancelledError:
            logger.info("Background email check loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in background cycle: {e}", exc_info=True)
        finally:
            # Heartbeat = "event loop alive", written every tick no matter what.
            update_heartbeat()

        try:
            await asyncio.sleep(config.CHECK_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Background sleep cancelled.")
            break

async def post_init(application: Application):
    logger.info("Initializing database...")
    await database.init_db()
    await group_assistant.init_tables()
    try:
        await application.bot.set_my_commands([
            BotCommand("bekleyenler", "Onay bekleyen taslaklar"),
            BotCommand("gruplar", "Gruplar ve bildirim modları"),
            BotCommand("ozet", "Grup özetini şimdi gönder"),
            BotCommand("kelimeler", "Anahtar kelime alarmları"),
            BotCommand("rapor", "Günlük rapor"),
            BotCommand("kontrol_et", "Gelen kutusunu hemen tara"),
            BotCommand("durum", "Sistem durumu"),
            BotCommand("iptaller", "İptal edilen yanıtlar"),
            BotCommand("hesaplar", "E-posta hesapları"),
            BotCommand("vitrin", "Vitrindeki uygulamalar"),
            BotCommand("iptal", "Yazma modundan çık"),
            BotCommand("yardim", "Yardım ve tüm özellikler"),
        ])
    except Exception as e:
        logger.warning(f"Could not set bot command menu: {e}")
    update_heartbeat()
    logger.info("Starting background worker task...")
    task = asyncio.create_task(background_loop(application))
    application.bot_data["bg_task"] = task
    
    # Notify admin
    try:
        await application.bot.send_message(
            chat_id=config.TELEGRAM_ADMIN_CHAT_ID,
            text="🚀 <b>Otonom AI E-posta Asistanı Başlatıldı!</b>\n\n"
                 "• <b>Sistem:</b> Debian Linux\n"
                 f"• <b>Kontrol Döngüsü:</b> Her {config.CHECK_INTERVAL} saniyede bir\n"
                 "• <b>Durum:</b> Aktif ve taranıyor\n\n"
                 "Yardım ve komutlar için /yardim yazabilirsiniz.",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Startup notification sent to admin {config.TELEGRAM_ADMIN_CHAT_ID}")
    except Exception as e:
        logger.info(f"Admin henüz bot ile etkileşim başlatmamış olabilir (/start bekleniyor): {e}")

async def post_shutdown(application: Application):
    logger.info("Application shutting down...")
    bg_task = application.bot_data.get("bg_task")
    if bg_task and not bg_task.done():
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutdown complete.")

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is missing in .env file!")
        sys.exit(1)

    logger.info("Building Telegram application...")
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .connect_timeout(20)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(20)
        .get_updates_read_timeout(40)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    setup_bot_handlers(application)
    logger.info("Starting Telegram polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()