import html
import asyncio
import logging
import psutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import config
import database
import mail_service
from ai_service import AIService
import app_catalog

logger = logging.getLogger(__name__)

# Conversation states for /hesap_ekle
STATE_EMAIL, STATE_IMAP, STATE_SMTP, STATE_PASSWORD = range(4)

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        if user_id != config.TELEGRAM_ADMIN_CHAT_ID and chat_id != config.TELEGRAM_ADMIN_CHAT_ID:
            logger.warning(f"Unauthorized access from user {user_id}, chat {chat_id}")
            if update.effective_message:
                await update.effective_message.reply_text("⛔ Yetkisiz erişim. Bu bot yalnızca yöneticisine yanıt verir.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def safe_html_truncate(text: str, max_chars: int = 3800) -> str:
    """Safely limits text length to prevent Telegram 4096 char limit errors."""
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars - 40] + "\n\n<i>[Uzunluk sınırı nedeniyle kısaltıldı]</i>"

def get_approval_keyboard(pending_id: int) -> InlineKeyboardMarkup:
    """
    Returns the 4-button approval keyboard:
    [✅ Gönder] | [🔄 Farklı Yanıt Üret]
    [✍️ Talimatla Düzenle] | [❌ İptal]
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Gönder", callback_data=f"send:{pending_id}"),
            InlineKeyboardButton("🔄 Farklı Yanıt Üret", callback_data=f"regen:{pending_id}")
        ],
        [
            InlineKeyboardButton("✍️ Talimatla Düzenle", callback_data=f"edit:{pending_id}"),
            InlineKeyboardButton("❌ İptal", callback_data=f"cancel:{pending_id}")
        ]
    ])

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 <b>Otonom AI E-posta Asistanına Hoş Geldiniz!</b>\n\n"
        "Bu bot, eklediğiniz e-posta hesaplarını arka planda periyodik olarak tarar, "
        "<b>apps.omergoktas.net</b> vitrinindeki güncel uygulamalarla entegre çalışır "
        "ve <b>Ömer Göktaş</b> adına <i>'Paylaşılmayan bilgi, bilgi değildir'</i> felsefesiyle yanıtlar üretir.\n\n"
        "⚡ <b>Akıllı Otonom Yanıt (Auto-Reply):</b>\n"
        "Gelen e-posta herhangi bir uygulamanın indirme/mağaza linkini veya vitrin adresini soruyorsa "
        "onay beklemeden doğrudan yanıtlar ve Telegram'a rapor gönderir.\n\n"
        "🎛️ <b>Gelişmiş Onay Seçenekleri:</b>\n"
        "• <b>[✅ Gönder]:</b> Hazırlanan yanıtı hemen iletir.\n"
        "• <b>[🔄 Farklı Yanıt Üret]:</b> Farklı ton ve yaklaşımla yeni taslak oluşturur.\n"
        "• <b>[✍️ Talimatla Düzenle]:</b> Verdiğiniz özel talimata göre taslağı yeniden şekillendirir.\n"
        "• <b>[❌ İptal]:</b> Yanıtı göndermeden sonlandırır.\n\n"
        "📌 <b>Kullanılabilir Komutlar:</b>\n"
        "• /hesaplar — Kayıtlı e-posta hesaplarını ve durumlarını listeler.\n"
        "• /hesap_ekle — Yeni bir e-posta hesabı ekler (Sihirbaz).\n"
        "• /hesap_sil &lt;id&gt; — Belirtilen hesabı kaldırır.\n"
        "• /vitrin — Vitrinde yayında olan uygulamaları listeler.\n"
        "• /durum — Sistem kaynakları, bekleyen onaylar ve veritabanı durumu.\n"
        "• /iptaller — Yanlışlıkla iptal edilen e-postaları listeler.\n"
        "• /geri_al &lt;id&gt; — İptal edilen e-postayı onay kuyruğuna geri alır.\n"
        "• /kontrol_et — Tüm hesapları anında manuel olarak kontrol eder.\n"
        "• /yardim — Bu yardım kılavuzunu görüntüler."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@admin_only
async def cmd_vitrin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apps = app_catalog.get_published_apps(force_refresh=True)
    if not apps:
        await update.message.reply_text("📭 Vitrinde yayında olan uygulama bulunamadı.")
        return

    text = f"📱 <b>Vitrin Uygulamaları ({config.SHOWCASE_BASE_URL}):</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for a in apps:
        platforms = a.get("platforms") or "Tümü"
        version = a.get("version") or "1.0.0"
        text += (
            f"• <b>{html.escape(a['title'])}</b> (v{html.escape(version)} - {html.escape(platforms)})\n"
            f"  Detay: {a['showcase_url']}\n\n"
        )
    text += "<i>Not: Bu veriler apps.sqlite veritabanından dinamik olarak okunur.</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@admin_only
async def cmd_hesaplar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = await database.get_accounts()
    if not accounts:
        await update.message.reply_text(
            "📭 Henüz kayıtlı e-posta hesabı bulunmuyor.\n"
            "Yeni hesap eklemek için /hesap_ekle komutunu kullanabilirsiniz.",
            parse_mode=ParseMode.HTML
        )
        return

    text = "📋 <b>Kayıtlı E-posta Hesapları:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for acc in accounts:
        status_icon = "🟢 Aktif" if acc["is_active"] else "🔴 Pasif"
        text += (
            f"<b>ID: {acc['id']}</b> | <code>{html.escape(acc['email_address'])}</code>\n"
            f"• Durum: {status_icon}\n"
            f"• IMAP: <code>{html.escape(acc['imap_server'])}:{acc['imap_port']}</code>\n"
            f"• SMTP: <code>{html.escape(acc['smtp_server'])}:{acc['smtp_port']}</code>\n"
            f"• İşlem: /hesap_sil_{acc['id']} | /durum_degis_{acc['id']}\n\n"
        )
    text += "Yeni bir hesap eklemek için: /hesap_ekle"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@admin_only
async def cmd_durum_degis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    part = text.split("_")[-1]
    if not part.isdigit():
        await update.message.reply_text("Geçersiz hesap ID'si.")
        return
    acc_id = int(part)
    acc = await database.get_account(acc_id)
    if not acc:
        await update.message.reply_text(f"ID {acc_id} olan hesap bulunamadı.")
        return
    new_status = 0 if acc["is_active"] else 1
    await database.toggle_account(acc_id, new_status)
    status_str = "🟢 Aktif" if new_status else "🔴 Pasif"
    await update.message.reply_text(f"Hesap <code>{acc['email_address']}</code> durumu güncellendi: {status_str}", parse_mode=ParseMode.HTML)

@admin_only
async def cmd_hesap_sil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    acc_id = None
    if args and args[0].isdigit():
        acc_id = int(args[0])
    elif update.message.text.startswith("/hesap_sil_"):
        part = update.message.text.split("_")[-1]
        if part.isdigit():
            acc_id = int(part)

    if not acc_id:
        await update.message.reply_text("Kullanım: <code>/hesap_sil &lt;id&gt;</code> (Örn: <code>/hesap_sil 1</code>)", parse_mode=ParseMode.HTML)
        return

    acc = await database.get_account(acc_id)
    if not acc:
        await update.message.reply_text(f"❌ ID {acc_id} olan hesap bulunamadı.", parse_mode=ParseMode.HTML)
        return

    await database.delete_account(acc_id)
    await update.message.reply_text(f"🗑️ <b>{html.escape(acc['email_address'])}</b> hesabı veritabanından silindi.", parse_mode=ParseMode.HTML)

@admin_only
async def cmd_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await database.get_stats()
    cpu_percent = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    apps_count = len(app_catalog.get_published_apps())

    msg = (
        "📊 <b>Sistem ve Asistan Durumu</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>Bot Durumu:</b> 🟢 Aktif ve Çalışıyor\n"
        f"📱 <b>Vitrin Uygulamaları:</b> {apps_count} adet yayında\n"
        f"💾 <b>Veritabanı:</b> {stats['db_size_kb']} KB (SQLite WAL Modu)\n"
        f"📧 <b>Hesaplar:</b> {stats['active_accounts']} aktif / {stats['total_accounts']} toplam\n"
        f"⏳ <b>Bekleyen Onaylar:</b> {stats['pending_count']} adet\n"
        f"✅ <b>Gönderilen Yanıtlar:</b> {stats['sent_count']} adet\n"
        f"❌ <b>İptal Edilenler:</b> {stats['cancelled_count']} adet\n"
        f"📬 <b>Kayıtlı İleti Kimlikleri:</b> {stats['processed_count']} adet\n\n"
        "🖥️ <b>Sunucu Kaynakları:</b>\n"
        f"• CPU Kullanımı: %{cpu_percent}\n"
        f"• RAM: %{mem.percent} ({round(mem.used / (1024**2), 1)} MB / {round(mem.total / (1024**2), 1)} MB)\n"
        f"• Disk: %{disk.percent} (Boş: {round(disk.free / (1024**3), 1)} GB)\n"
        f"• Otomatik Kontrol Aralığı: {config.CHECK_INTERVAL} saniye"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ConversationHandler for /hesap_ekle
@admin_only
async def start_hesap_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_acc"] = {}
    msg = (
        "➕ <b>Yeni E-posta Hesabı Ekleme Sihirbazı</b>\n\n"
        "Lütfen eklemek istediğiniz e-posta adresini giriniz:\n"
        "<i>(İşlemi iptal etmek için istediğiniz zaman /iptal yazabilirsiniz)</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return STATE_EMAIL

@admin_only
async def step_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email_text = update.message.text.strip().lower()
    if "@" not in email_text or "." not in email_text:
        await update.message.reply_text("❌ Lütfen geçerli bir e-posta adresi giriniz (Örn: ornek@gmail.com):")
        return STATE_EMAIL

    context.user_data["new_acc"]["email"] = email_text
    
    default_imap = "imap.gmail.com:993"
    default_smtp = "smtp.gmail.com:587"
    if "outlook" in email_text or "hotmail" in email_text:
        default_imap = "outlook.office365.com:993"
        default_smtp = "smtp.office365.com:587"
    elif "yandex" in email_text:
        default_imap = "imap.yandex.com:993"
        default_smtp = "smtp.yandex.com:465"

    context.user_data["new_acc"]["default_imap"] = default_imap
    context.user_data["new_acc"]["default_smtp"] = default_smtp

    msg = (
        f"📧 E-posta: <code>{html.escape(email_text)}</code>\n\n"
        f"📥 <b>IMAP Sunucu ve Port</b> bilgisini giriniz.\n"
        f"Önerilen varsayılan: <code>{default_imap}</code>\n\n"
        f"Önerileni kullanmak için <b>varsayilan</b> veya <b>gec</b> yazabilirsiniz, "
        f"farklıysa <code>sunucu:port</code> formatında yazınız:"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return STATE_IMAP

@admin_only
async def step_imap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    default_imap = context.user_data["new_acc"].get("default_imap", "imap.gmail.com:993")
    
    if text.lower() in ["varsayilan", "varsayılan", "gec", "geç", "ok", "yes"]:
        target = default_imap
    else:
        target = text

    if ":" in target:
        server, port = target.split(":", 1)
        port = int(port.strip()) if port.strip().isdigit() else 993
    else:
        server = target.strip()
        port = 993

    context.user_data["new_acc"]["imap_server"] = server
    context.user_data["new_acc"]["imap_port"] = port

    default_smtp = context.user_data["new_acc"].get("default_smtp", "smtp.gmail.com:587")
    msg = (
        f"📥 IMAP: <code>{html.escape(server)}:{port}</code> olarak ayarlandı.\n\n"
        f"📤 <b>SMTP Sunucu ve Port</b> bilgisini giriniz.\n"
        f"Önerilen varsayılan: <code>{default_smtp}</code>\n\n"
        f"Önerileni kullanmak için <b>varsayilan</b> veya <b>gec</b> yazabilirsiniz, "
        f"farklıysa <code>sunucu:port</code> formatında yazınız:"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return STATE_SMTP

@admin_only
async def step_smtp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    default_smtp = context.user_data["new_acc"].get("default_smtp", "smtp.gmail.com:587")
    
    if text.lower() in ["varsayilan", "varsayılan", "gec", "geç", "ok", "yes"]:
        target = default_smtp
    else:
        target = text

    if ":" in target:
        server, port = target.split(":", 1)
        port = int(port.strip()) if port.strip().isdigit() else 587
    else:
        server = target.strip()
        port = 587

    context.user_data["new_acc"]["smtp_server"] = server
    context.user_data["new_acc"]["smtp_port"] = port

    msg = (
        f"📤 SMTP: <code>{html.escape(server)}:{port}</code> olarak ayarlandı.\n\n"
        f"🔑 Lütfen e-posta sağlayıcınızdan aldığınız <b>Uygulama Şifresini (App Password)</b> giriniz:\n\n"
        f"<i>Not: Gmail için Google Hesabı -> Güvenlik -> 2 Adımlı Doğrulama -> Uygulama Şifreleri bölümünden 16 haneli bir şifre üretmelisiniz.</i>"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return STATE_PASSWORD

@admin_only
async def step_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip().replace(" ", "")
    acc_data = context.user_data.get("new_acc", {})
    email_addr = acc_data.get("email")
    imap_server = acc_data.get("imap_server")
    imap_port = acc_data.get("imap_port")
    smtp_server = acc_data.get("smtp_server")
    smtp_port = acc_data.get("smtp_port")

    await update.message.reply_text("⏳ <i>Bağlantı ayarları test ediliyor, lütfen bekleyiniz...</i>", parse_mode=ParseMode.HTML)

    ok, err_msg = await asyncio.to_thread(
        mail_service.test_account_connection,
        email_addr, imap_server, imap_port, smtp_server, smtp_port, password
    )

    if not ok:
        await update.message.reply_text(
            f"❌ <b>Bağlantı Başarısız Oldu!</b>\n\n"
            f"<code>{html.escape(err_msg)}</code>\n\n"
            f"Lütfen şifrenizi kontrol edip tekrar giriniz veya vazgeçmek için /iptal yazınız.",
            parse_mode=ParseMode.HTML
        )
        return STATE_PASSWORD

    acc_id = await database.add_account(
        email_address=email_addr,
        imap_server=imap_server,
        imap_port=imap_port,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        app_password=password,
        check_interval_seconds=config.CHECK_INTERVAL
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ <b>Hesap Başarıyla Eklendi ve Doğrulandı!</b>\n\n"
        f"• <b>ID:</b> {acc_id}\n"
        f"• <b>E-posta:</b> <code>{html.escape(email_addr)}</code>\n"
        f"• <b>IMAP:</b> <code>{html.escape(imap_server)}:{imap_port}</code>\n"
        f"• <b>SMTP:</b> <code>{html.escape(smtp_server)}:{smtp_port}</code>\n"
        f"• <b>Durum:</b> 🟢 Aktif (Taranıyor)",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

@admin_only
async def cancel_hesap_ekle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Hesap ekleme işlemi iptal edildi.")
    return ConversationHandler.END

# Inline button callback handler
@admin_only
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if not data or ":" not in data:
        await query.answer("Geçersiz işlem.")
        return

    action, reply_id_str = data.split(":", 1)
    if not reply_id_str.isdigit():
        await query.answer("Geçersiz ID.")
        return

    reply_id = int(reply_id_str)
    pending = await database.get_pending_reply(reply_id)

    if not pending:
        await query.answer("Bu kayıt veritabanında bulunamadı.")
        return

    if action == "restore":
        if pending["status"] != "CANCELLED":
            status_tr = "Gönderilmiş" if pending["status"] == "SENT" else "Zaten Beklemede"
            await query.answer(f"Bu kayıt iptal edilmiş durumda değil ({status_tr}).", show_alert=True)
            return

        await database.update_reply_status(reply_id, "PENDING")
        await query.answer("↩️ İptal geri alındı, onay kuyruğuna eklendi!", show_alert=True)

        restore_text = (
            f"↩️ <b>E-posta Onay Kuyruğuna Geri Alındı!</b> (Hesap: <code>{html.escape(pending['email_address'])}</code>)\n"
            f"<b>Kimden:</b> {html.escape(pending['sender'])}\n"
            f"<b>Konu:</b> {html.escape(pending['subject'])}\n\n"
            f"📌 <b>Özet:</b>\n{html.escape(pending['gemini_summary'])}\n\n"
            f"✍️ <b>Önerilen Yanıt:</b>\n{html.escape(safe_html_truncate(pending['draft_reply'], 2500))}"
        )
        try:
            await query.edit_message_text(
                text=restore_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_approval_keyboard(reply_id)
            )
        except Exception as e:
            logger.error(f"Error updating message after restore: {e}")
        return

    if pending["status"] != "PENDING":
        status_tr = "Gönderilmiş" if pending["status"] == "SENT" else "İptal Edilmiş"
        await query.answer(f"Bu e-posta zaten işlem görmüş ({status_tr}).", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if action == "send":
        await query.answer("E-posta gönderiliyor...")
        account = {
            "id": pending["account_id"],
            "email_address": pending["email_address"],
            "smtp_server": pending["smtp_server"],
            "smtp_port": pending["smtp_port"],
            "imap_server": pending["imap_server"],
            "imap_port": pending["imap_port"],
            "app_password": pending["app_password"]
        }

        sent_ok, err_str = await asyncio.to_thread(
            mail_service.send_reply_email,
            account,
            pending["sender"],
            pending["subject"] or "Re:",
            pending["message_id"],
            pending["draft_reply"]
        )

        if sent_ok:
            await asyncio.to_thread(mail_service.mark_email_as_seen, account, pending["message_id"])
            await database.update_reply_status(reply_id, "SENT")

            original_text = query.message.text or ""
            updated_text = (
                f"{original_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ <b>YANIT GÖNDERİLDİ</b>\n"
                f"🗓️ <i>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</i>"
            )
            try:
                await query.edit_message_text(text=updated_text, parse_mode=ParseMode.HTML, reply_markup=None)
            except Exception:
                await query.message.reply_text(f"✅ <b>ID {reply_id} yanıtı başarıyla gönderildi!</b>", parse_mode=ParseMode.HTML)
        else:
            await query.message.reply_text(
                f"❌ <b>Gönderim Hatası:</b>\n<code>{html.escape(err_str)}</code>",
                parse_mode=ParseMode.HTML
            )

    elif action == "regen":
        await query.answer("🔄 Yeni yanıt taslağı üretiliyor, lütfen bekleyiniz...")
        ai_service = AIService()
        new_draft = await asyncio.to_thread(
            ai_service.regenerate_reply,
            pending["sender"],
            pending["subject"],
            pending["incoming_snippet"] or "",
            pending["draft_reply"] or ""
        )

        await database.update_pending_draft(reply_id, new_draft)

        time_str = datetime.now().strftime('%H:%M:%S')
        updated_text = (
            f"📩 <b>Yeni E-posta!</b> (Hesap: <code>{html.escape(pending['email_address'])}</code>)\n"
            f"<b>Kimden:</b> {html.escape(pending['sender'])}\n"
            f"<b>Konu:</b> {html.escape(pending['subject'])}\n\n"
            f"📌 <b>Özet:</b>\n{html.escape(pending['gemini_summary'])}\n\n"
            f"✍️ <b>Önerilen Yanıt (Farklı Tonla Yenilendi - {time_str}):</b>\n{html.escape(safe_html_truncate(new_draft, 2500))}"
        )

        try:
            await query.edit_message_text(
                text=updated_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_approval_keyboard(reply_id)
            )
        except Exception as e:
            logger.error(f"Error updating message after regen: {e}")

    elif action == "edit":
        await query.answer()
        context.user_data["editing_reply_id"] = reply_id
        context.user_data["editing_chat_id"] = query.message.chat_id
        context.user_data["editing_message_id"] = query.message.message_id

        prompt_msg = (
            f"✍️ <b>Taslak Düzenleme Modu (ID: {reply_id})</b>\n\n"
            "Lütfen bu e-posta yanıtına eklemek veya değiştirmek istediğiniz talimatı yazınız:\n"
            "<i>(Örn: 'Haftaya çarşamba saat 14:00'te görüşelim de' veya 'Fiyat teklifi sor')</i>\n\n"
            "İptal etmek için /iptal yazabilirsiniz."
        )
        await query.message.reply_text(prompt_msg, parse_mode=ParseMode.HTML)

    elif action == "cancel":
        await query.answer("Yanıt iptal edildi.")
        await database.update_reply_status(reply_id, "CANCELLED")

        original_text = query.message.text or ""
        updated_text = (
            f"{original_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"❌ <b>YANIT İPTAL EDİLDİ</b>\n"
            f"🗓️ <i>{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</i>\n"
            f"<i>(Yanlışlıkla iptal ettiyseniz aşağıdaki butona basarak geri alabilirsiniz)</i>"
        )
        restore_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ İptali Geri Al (Yeniden Aç)", callback_data=f"restore:{reply_id}")]
        ])
        try:
            await query.edit_message_text(text=updated_text, parse_mode=ParseMode.HTML, reply_markup=restore_markup)
        except Exception:
            await query.message.reply_text(
                f"❌ <b>ID {reply_id} yanıtı iptal edildi.</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=restore_markup
            )

# Message handler for drafting instructions
@admin_only
async def handle_edit_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    editing_id = context.user_data.get("editing_reply_id")
    if not editing_id:
        return

    instruction = update.message.text.strip()
    if instruction.lower() in ["/iptal", "iptal"]:
        context.user_data.pop("editing_reply_id", None)
        context.user_data.pop("editing_chat_id", None)
        context.user_data.pop("editing_message_id", None)
        await update.message.reply_text("❌ Taslak düzenleme iptal edildi.")
        return

    pending = await database.get_pending_reply(editing_id)
    if not pending or pending["status"] != "PENDING":
        context.user_data.pop("editing_reply_id", None)
        context.user_data.pop("editing_chat_id", None)
        context.user_data.pop("editing_message_id", None)
        await update.message.reply_text("Bu e-posta artık düzenlenemez (zaten gönderilmiş veya iptal edilmiş).")
        return

    wait_msg = await update.message.reply_text("⏳ <i>Talimatınız doğrultusunda yanıt şekillendiriliyor...</i>", parse_mode=ParseMode.HTML)

    ai_service = AIService()
    refined_draft = await asyncio.to_thread(
        ai_service.refine_reply_with_instruction,
        pending["sender"],
        pending["subject"],
        pending["incoming_snippet"] or "",
        pending["draft_reply"] or "",
        instruction
    )

    await database.update_pending_draft(editing_id, refined_draft)

    orig_chat_id = context.user_data.pop("editing_chat_id", None)
    orig_msg_id = context.user_data.pop("editing_message_id", None)
    context.user_data.pop("editing_reply_id", None)

    notification_text = (
        f"📩 <b>Yeni E-posta!</b> (Hesap: <code>{html.escape(pending['email_address'])}</code>)\n"
        f"<b>Kimden:</b> {html.escape(pending['sender'])}\n"
        f"<b>Konu:</b> {html.escape(pending['subject'])}\n\n"
        f"📌 <b>Özet:</b>\n{html.escape(pending['gemini_summary'])}\n\n"
        f"✍️ <b>Önerilen Yanıt (Talimatınızla Düzenlendi):</b>\n{html.escape(safe_html_truncate(refined_draft, 2500))}"
    )

    if orig_chat_id and orig_msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=orig_chat_id,
                message_id=orig_msg_id,
                text=notification_text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_approval_keyboard(editing_id)
            )
        except Exception as e:
            logger.debug(f"Could not edit original message: {e}")

    try:
        await wait_msg.delete()
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ <b>Taslak başarıyla güncellendi!</b>\n\n"
        f"✍️ <b>Yeni Yanıt:</b>\n{html.escape(refined_draft)}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_approval_keyboard(editing_id)
    )

# Email checking and autonomous dispatch cycle
async def check_emails_cycle(bot) -> int:
    accounts = await database.get_accounts(active_only=True)
    if not accounts:
        return 0

    ai_service = AIService()
    new_found = 0

    for acc in accounts:
        try:
            unseen_emails = await asyncio.to_thread(mail_service.fetch_unseen_emails, acc)
            for m in unseen_emails:
                msg_id = m["message_id"]
                if await database.is_message_processed(acc["id"], msg_id):
                    continue

                sender = m["sender"]
                subject = m["subject"]

                # 1. STEP: MAILING LIST & BULK IGNORE FILTER (FIRST STEP BEFORE GEMINI)
                if m.get("is_ignored"):
                    reason = m.get("ignore_reason") or "Mailing List / Kara Liste"
                    logger.info(f"🚫 [FİLTRE - YOK SAYILDI] Konu: '{subject}' | Gönderen: '{sender}' | Sebep: {reason}")
                    await database.mark_message_processed(acc["id"], msg_id)
                    continue

                await database.mark_message_processed(acc["id"], msg_id)

                body = m["body"]

                # 2. STEP: Gemini analysis with dynamic app catalog
                ai_res = await asyncio.to_thread(ai_service.analyze_email, sender, subject, body)
                summary = ai_res.get("summary", "")
                reply_body = ai_res.get("reply_body", "")
                is_link_request = ai_res.get("is_link_request", False)
                requested_app = ai_res.get("requested_app")
                auto_send = ai_res.get("auto_send", False)
                error_note = ai_res.get("error_note")

                # Store pending reply in DB
                pending_id = await database.add_pending_reply(
                    account_id=acc["id"],
                    message_id=msg_id,
                    sender=sender,
                    subject=subject,
                    incoming_snippet=body[:500],
                    gemini_summary=summary,
                    draft_reply=reply_body
                )

                # 3. STEP: AUTONOMOUS AUTO-REPLY LOGIC
                if auto_send:
                    logger.info(f"🚀 Auto-reply triggered for '{subject}' from '{sender}' (Requested app: {requested_app})")
                    sent_ok, err_str = await asyncio.to_thread(
                        mail_service.send_reply_email,
                        acc,
                        sender,
                        subject,
                        msg_id,
                        reply_body
                    )

                    if sent_ok:
                        await asyncio.to_thread(mail_service.mark_email_as_seen, acc, msg_id)
                        await database.update_reply_status(pending_id, "SENT")

                        app_label = requested_app or "Uygulama / Vitrin"
                        report_text = (
                            f"🚀 <b>[Otomatik Yanıt Gönderildi]</b>\n"
                            f"<b>Hesap:</b> <code>{html.escape(acc['email_address'])}</code>\n"
                            f"<b>Kimden:</b> {html.escape(sender)}\n"
                            f"<b>Konu:</b> {html.escape(subject)}\n"
                            f"<b>İşlem:</b> <i>{html.escape(app_label)}</i> için güncel indirme bağlantısı iletildi.\n\n"
                            f"📌 <b>Özet:</b>\n{html.escape(summary)}\n\n"
                            f"✍️ <b>İletilen Yanıt:</b>\n{html.escape(safe_html_truncate(reply_body, 2500))}"
                        )

                        await bot.send_message(
                            chat_id=config.TELEGRAM_ADMIN_CHAT_ID,
                            text=report_text,
                            parse_mode=ParseMode.HTML
                        )
                        new_found += 1
                        continue
                    else:
                        logger.error(f"Auto-send failed via SMTP: {err_str}. Falling back to manual approval.")

                # 4. STEP: MANUAL APPROVAL FLOW WITH 4 BUTTONS
                note_html = f"\n\n<i>{html.escape(error_note)}</i>" if error_note else ""
                notification_text = (
                    f"📩 <b>Yeni E-posta!</b> (Hesap: <code>{html.escape(acc['email_address'])}</code>)\n"
                    f"<b>Kimden:</b> {html.escape(sender)}\n"
                    f"<b>Konu:</b> {html.escape(subject)}\n\n"
                    f"📌 <b>Özet:</b>\n{html.escape(summary)}\n\n"
                    f"✍️ <b>Önerilen Yanıt:</b>\n{html.escape(safe_html_truncate(reply_body, 2500))}"
                    f"{note_html}"
                )

                await bot.send_message(
                    chat_id=config.TELEGRAM_ADMIN_CHAT_ID,
                    text=notification_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_approval_keyboard(pending_id)
                )
                new_found += 1
        except Exception as e:
            logger.error(f"Error checking emails for {acc.get('email_address')}: {e}", exc_info=True)

    return new_found

@admin_only
async def cmd_kontrol_et(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 <i>E-posta hesapları taranıyor, lütfen bekleyiniz...</i>", parse_mode=ParseMode.HTML)
    count = await check_emails_cycle(context.bot)
    if count == 0:
        await update.message.reply_text("✅ Tarama tamamlandı. Yeni okunmamış e-posta bulunamadı.")
    else:
        await update.message.reply_text(f"✅ Tarama tamamlandı. <b>{count}</b> adet e-posta işlendi.", parse_mode=ParseMode.HTML)

@admin_only
async def cmd_iptaller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancelled = await database.get_cancelled_replies(limit=10)
    if not cancelled:
        await update.message.reply_text("📭 İptal edilmiş herhangi bir e-posta yanıtı bulunmuyor.")
        return

    text = "📋 <b>Son İptal Edilen Yanıtlar:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for r in cancelled:
        snippet = (r.get("incoming_snippet") or "")[:100].replace("\n", " ")
        text += (
            f"• <b>ID: {r['id']}</b> | Kimden: {html.escape(r.get('sender') or '')}\n"
            f"  Konu: {html.escape(r.get('subject') or '(Konusuz)')}\n"
            f"  👉 Geri Almak İçin: /geri_al_{r['id']}\n\n"
        )
    text += "<i>Bir e-postayı onay kuyruğuna geri almak için yukarıdaki mavi /geri_al_... linkine tıklayabilir veya <code>/geri_al &lt;id&gt;</code> yazabilirsiniz.</i>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@admin_only
async def cmd_geri_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    reply_id = None
    if args and args[0].isdigit():
        reply_id = int(args[0])
    elif update.message.text.startswith("/geri_al_"):
        part = update.message.text.split("_")[-1]
        if part.isdigit():
            reply_id = int(part)

    if not reply_id:
        await update.message.reply_text(
            "Kullanım: <code>/geri_al &lt;id&gt;</code> (Örn: <code>/geri_al 7</code>)\n"
            "İptal edilen tüm mailleri listelemek için: /iptaller",
            parse_mode=ParseMode.HTML
        )
        return

    pending = await database.get_pending_reply(reply_id)
    if not pending:
        await update.message.reply_text(f"❌ ID {reply_id} olan kayıt veritabanında bulunamadı.")
        return

    if pending["status"] == "SENT":
        await update.message.reply_text(f"⚠️ ID {reply_id} yanıtı zaten gönderilmiş, geri alınamaz.")
        return

    await database.update_reply_status(reply_id, "PENDING")

    restore_text = (
        f"↩️ <b>E-posta Onay Kuyruğuna Geri Alındı! (ID: {reply_id})</b>\n"
        f"<b>Hesap:</b> <code>{html.escape(pending['email_address'])}</code>\n"
        f"<b>Kimden:</b> {html.escape(pending['sender'])}\n"
        f"<b>Konu:</b> {html.escape(pending['subject'])}\n\n"
        f"📌 <b>Özet:</b>\n{html.escape(pending['gemini_summary'])}\n\n"
        f"✍️ <b>Önerilen Yanıt:</b>\n{html.escape(safe_html_truncate(pending['draft_reply'], 2500))}"
    )

    await update.message.reply_text(
        text=restore_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_approval_keyboard(reply_id)
    )

def setup_bot_handlers(application: Application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("hesap_ekle", start_hesap_ekle)],
        states={
            STATE_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_email)],
            STATE_IMAP: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_imap)],
            STATE_SMTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_smtp)],
            STATE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, step_password)],
        },
        fallbacks=[CommandHandler("iptal", cancel_hesap_ekle)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("yardim", cmd_start))
    application.add_handler(CommandHandler("vitrin", cmd_vitrin))
    application.add_handler(CommandHandler("hesaplar", cmd_hesaplar))
    application.add_handler(CommandHandler("durum", cmd_durum))
    application.add_handler(CommandHandler("kontrol_et", cmd_kontrol_et))
    application.add_handler(CommandHandler("iptaller", cmd_iptaller))
    application.add_handler(CommandHandler("geri_al", cmd_geri_al))
    application.add_handler(MessageHandler(filters.Regex(r"^/geri_al_\d+"), cmd_geri_al))
    application.add_handler(CommandHandler("hesap_sil", cmd_hesap_sil))
    application.add_handler(MessageHandler(filters.Regex(r"^/hesap_sil_\d+"), cmd_hesap_sil))
    application.add_handler(MessageHandler(filters.Regex(r"^/durum_degis_\d+"), cmd_durum_degis))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Text handler for edit instructions (must be after command/conversation handlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_instruction))