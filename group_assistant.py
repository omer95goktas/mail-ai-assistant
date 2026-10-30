"""
Group Assistant
---------------
Mailing-list / Google Groups mails are still marked as read, but now they are
archived and the admin is kept informed like a personal assistant:

* Per-group modes: OZET (digest every N hours), ANLIK (instant), SESSIZ (silent)
* Keyword alarms (even for silent groups)
* Quiet hours (no digests at night; accumulated mails come in the morning)
* Morning report
* Natural-language control via Gemini ("GEÖP'ten mail atma", "şimdi özet ver" ...)
* Q&A over the archived group mails
"""
import re
import json
import html
import time
import asyncio
import logging
from datetime import datetime

import aiosqlite
from google.genai import types

import config
import database
import app_catalog

logger = logging.getLogger(__name__)

MODES = {"OZET": "📰 Özet", "ANLIK": "⚡ Anlık", "SESSIZ": "🔕 Sessiz"}
DEFAULT_SETTINGS = {
    "digest_interval_hours": "3",
    "quiet_start": "0",
    "quiet_end": "8",
    "default_mode": "OZET",
    "last_digest_ts": "0",
    "last_morning_date": "",
}
BASE_KEYWORDS = ["Ömer Göktaş", "Omer Goktas"]


# ======================= helpers =======================
def tr_lower(s: str) -> str:
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def esc(s) -> str:
    return html.escape(str(s or ""))


_FOOTER_MARKERS = [
    "-=-=-=-=-=-=-=-=-=-=-=-",                       # groups.io
    "You received this message because you are subscribed",  # Google Groups (EN)
    "Bu iletiyi, Google Grupları",                   # Google Groups (TR)
    "Bu mesajı, Google Grupları",
    "To unsubscribe from this group",
    "Bu gruptan aboneliğinizi iptal etmek",
]


def clean_body(body: str) -> str:
    """Removes quoted history and mailing-list footers."""
    text = body or ""
    for mk in _FOOTER_MARKERS:
        i = text.find(mk)
        if i != -1:
            text = text[:i]
    lines = [l for l in text.splitlines() if not l.lstrip().startswith(">")]
    text = "\n".join(lines)
    # cut typical reply headers ("On ... wrote:", "... tarihinde şunu yazdı:")
    text = re.split(r"\n.{0,120}(wrote:|şunu yazdı:|yazdı:)\s*\n", text)[0]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def keyword_haystack(subject: str, body: str) -> str:
    """Text used for keyword alarms: no e-mail addresses / URLs (subscriber footers caused false alarms)."""
    t = f"{subject}\n{clean_body(body)}"
    t = re.sub(r"\S+@\S+", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    return tr_lower(t)


def plain_ai_text(s: str) -> str:
    """Gemini sometimes returns markdown; make it screen-reader friendly plain text."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s or "")
    s = re.sub(r"(?m)^\s*[\*\-]\s+", "• ", s)
    s = s.replace("*", "").replace("#", "")
    return s.strip()


def extract_group_info(msg) -> tuple:
    """Returns (group_key, group_name) for mailing-list mails, else (None, None)."""
    from mail_service import decode_mime_words
    list_id = decode_mime_words(msg.get("List-Id", "") or "")
    key, name = None, None
    if list_id:
        m = re.search(r"<([^>]+)>", list_id)
        key = (m.group(1) if m else list_id).strip().lower()
        desc = re.sub(r"<[^>]*>", "", list_id).strip().strip('"').strip()
        name = desc or None
    else:
        addrs = " ".join(str(msg.get(h, "")) for h in ("To", "Cc", "Reply-To", "From")).lower()
        m = re.search(r"([\w.+-]+)@(googlegroups\.com|yahoogroups\.com)", addrs)
        if m:
            key = f"{m.group(1)}.{m.group(2)}"
    if not key:
        return None, None
    if not name:
        subj = decode_mime_words(msg.get("Subject", "") or "")
        tag = re.search(r"\[([^\]]{2,40})\]", subj) or re.search(r"(?:^|\s)([A-ZÇĞİÖŞÜ]{2,10})-\s", subj)
        name = tag.group(1).strip() if tag else key.split(".")[0]
    if not name or name.isdigit() or "alerts.google" in key:
        from email.utils import parseaddr
        disp = parseaddr(decode_mime_words(msg.get("From", "") or ""))[0].strip()
        name = disp or ("Google Uyarıları" if "alerts.google" in key else key.split(".")[0])
    return key, name[:60]


# ======================= DB layer =======================
async def init_tables():
    async with database.get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_settings (
                group_key TEXT PRIMARY KEY,
                name TEXT,
                mode TEXT DEFAULT 'OZET',
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                msg_count INTEGER DEFAULT 0
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS group_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_key TEXT NOT NULL,
                message_id TEXT,
                sender TEXT,
                subject TEXT,
                body TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                instant_pending INTEGER DEFAULT 0,
                keyword_hit TEXT,
                digested INTEGER DEFAULT 0,
                UNIQUE(group_key, message_id)
            )""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_gm_digest ON group_messages(digested)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_gm_instant ON group_messages(instant_pending)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_gm_time ON group_messages(received_at)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS assistant_settings (key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watch_keywords (
                keyword TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        initial = dict(DEFAULT_SETTINGS)
        initial["last_digest_ts"] = str(time.time())  # first digest one interval after install
        for k, v in initial.items():
            await db.execute("INSERT OR IGNORE INTO assistant_settings(key, value) VALUES(?, ?)", (k, v))
        cur = await db.execute("SELECT COUNT(*) FROM watch_keywords")
        if (await cur.fetchone())[0] == 0:
            kws = list(BASE_KEYWORDS)
            try:
                kws += [a["title"] for a in app_catalog.get_published_apps(force_refresh=True) if a.get("title")]
            except Exception:
                pass
            for kw in kws:
                await db.execute("INSERT OR IGNORE INTO watch_keywords(keyword) VALUES(?)", (kw,))
        await db.execute("DELETE FROM group_messages WHERE received_at < datetime('now','-45 days')")
        await db.commit()


async def get_setting(key: str) -> str:
    async with database.get_db() as db:
        cur = await db.execute("SELECT value FROM assistant_settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else DEFAULT_SETTINGS.get(key, "")


async def set_setting(key: str, value):
    async with database.get_db() as db:
        await db.execute("INSERT OR REPLACE INTO assistant_settings(key, value) VALUES(?, ?)", (key, str(value)))
        await db.commit()


async def get_keywords() -> list:
    async with database.get_db() as db:
        cur = await db.execute("SELECT keyword FROM watch_keywords ORDER BY keyword")
        return [r[0] for r in await cur.fetchall()]


async def add_keyword(kw: str) -> bool:
    async with database.get_db() as db:
        cur = await db.execute("INSERT OR IGNORE INTO watch_keywords(keyword) VALUES(?)", (kw.strip(),))
        await db.commit()
        return cur.rowcount > 0


async def remove_keyword(kw: str) -> bool:
    async with database.get_db() as db:
        cur = await db.execute("DELETE FROM watch_keywords WHERE lower(keyword)=lower(?)", (kw.strip(),))
        await db.commit()
        return cur.rowcount > 0


async def get_groups() -> list:
    async with database.get_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT g.*, (SELECT COUNT(*) FROM group_messages m
                         WHERE m.group_key=g.group_key AND m.received_at > datetime('now','-1 day')) AS last24
            FROM group_settings g ORDER BY g.last_seen DESC""")
        return [dict(r) for r in await cur.fetchall()]


async def set_group_mode(group_key: str, mode: str) -> bool:
    async with database.get_db() as db:
        cur = await db.execute("UPDATE group_settings SET mode=? WHERE group_key=?", (mode, group_key))
        if mode != "ANLIK":
            await db.execute("UPDATE group_messages SET instant_pending=0 WHERE group_key=? AND keyword_hit IS NULL", (group_key,))
        await db.commit()
        return cur.rowcount > 0


async def get_group(group_key: str):
    async with database.get_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM group_settings WHERE group_key=?", (group_key,))
        r = await cur.fetchone()
        return dict(r) if r else None


async def store_group_message(group_key: str, group_name: str, message_id: str,
                              sender: str, subject: str, body: str):
    """Called from the fetch phase. Durable: instant/keyword notification flags are persisted."""
    default_mode = await get_setting("default_mode")
    async with database.get_db() as db:
        await db.execute("""
            INSERT INTO group_settings(group_key, name, mode) VALUES(?, ?, ?)
            ON CONFLICT(group_key) DO UPDATE SET last_seen=CURRENT_TIMESTAMP, msg_count=msg_count+1
        """, (group_key, group_name, default_mode))
        cur = await db.execute("SELECT mode FROM group_settings WHERE group_key=?", (group_key,))
        mode = (await cur.fetchone())[0]

        kw_hit = None
        hay = keyword_haystack(subject, body)
        cur = await db.execute("SELECT keyword FROM watch_keywords")
        for (kw,) in await cur.fetchall():
            if tr_lower(kw) in hay:
                kw_hit = kw
                break

        instant = 1 if (mode == "ANLIK" or kw_hit) else 0
        await db.execute("""
            INSERT OR IGNORE INTO group_messages(group_key, message_id, sender, subject, body, instant_pending, keyword_hit)
            VALUES(?, ?, ?, ?, ?, ?, ?)
        """, (group_key, message_id, sender, subject, clean_body(body)[:6000], instant, kw_hit))
        await db.commit()


# ======================= Gemini =======================
def _gemini_call(prompt: str, json_mode: bool = False, temperature: float = 0.3) -> str:
    from ai_service import AIService
    svc = AIService()
    if not svc.client:
        raise RuntimeError("Gemini istemcisi yok")
    last = None
    for m in [svc.model, "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]:
        try:
            cfg = types.GenerateContentConfig(temperature=temperature,
                                              response_mime_type="application/json" if json_mode else None)
            res = svc.client.models.generate_content(model=m, contents=prompt, config=cfg)
            text = (res.text or "").strip()
            if text.startswith("```"):
                text = "\n".join(l for l in text.splitlines() if not l.startswith("```")).strip()
            if text:
                return text
        except Exception as e:
            last = e
            logger.warning(f"Group assistant Gemini {m} failed: {e}")
    raise RuntimeError(f"Gemini yanıt vermedi: {last}")


async def gemini(prompt: str, json_mode: bool = False, timeout: int = 120, temperature: float = 0.3) -> str:
    return await asyncio.wait_for(asyncio.to_thread(_gemini_call, prompt, json_mode, temperature), timeout=timeout)


# ======================= Keyboards =======================
def short_id(group_key: str) -> str:
    import hashlib
    return hashlib.md5(group_key.encode("utf-8")).hexdigest()[:12]


async def resolve_short_id(sid: str):
    for g in await get_groups():
        if short_id(g["group_key"]) == sid:
            return g
    return None


def group_mode_keyboard(group_key: str, current: str = None):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    btns = []
    for mode, label in MODES.items():
        if mode != current:
            btns.append(InlineKeyboardButton(label, callback_data=f"gmode:{mode}:{short_id(group_key)}"))
    return InlineKeyboardMarkup([btns])


# ======================= Scheduled jobs =======================
def _in_quiet_hours(qs: int, qe: int, hour: int) -> bool:
    if qs == qe:
        return False
    return (qs <= hour < qe) if qs < qe else (hour >= qs or hour < qe)


async def send_instant_notifications(bot, send):
    async with database.get_db() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT m.*, g.name AS group_name, g.mode AS group_mode FROM group_messages m
            JOIN group_settings g ON g.group_key=m.group_key
            WHERE m.instant_pending=1 ORDER BY m.id ASC LIMIT 10""")
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        head = (f"🔔 <b>Anahtar kelime alarmı:</b> “{esc(r['keyword_hit'])}”\n" if r.get("keyword_hit")
                else "⚡ <b>Anlık grup bildirimi</b>\n")
        body = re.sub(r"\n{3,}", "\n\n", (r.get("body") or "").strip())
        # drop quoted history for readability
        body = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith(">"))[:900]
        text = (f"{head}<b>Grup:</b> {esc(r['group_name'])}\n<b>Kimden:</b> {esc(r['sender'])}\n"
                f"<b>Konu:</b> {esc(r['subject'])}\n\n{esc(body)}")
        await send(bot, text, reply_markup=group_mode_keyboard(r["group_key"], r["group_mode"]))
        async with database.get_db() as db:
            await db.execute("UPDATE group_messages SET instant_pending=0, digested=1 WHERE id=?", (r["id"],))
            await db.commit()


async def build_and_send_digest(bot, send, manual: bool = False) -> bool:
    async with database.get_db() as db:
        db.row_factory = aiosqlite.Row
        # silent / instant groups never go into digests
        await db.execute("""UPDATE group_messages SET digested=1 WHERE digested=0 AND instant_pending=0 AND group_key IN
                            (SELECT group_key FROM group_settings WHERE mode IN ('SESSIZ','ANLIK'))""")
        await db.commit()
        cur = await db.execute("""
            SELECT m.id, m.group_key, m.sender, m.subject, m.body, g.name AS group_name
            FROM group_messages m JOIN group_settings g ON g.group_key=m.group_key
            WHERE m.digested=0 AND m.instant_pending=0 AND g.mode='OZET'
            ORDER BY m.group_key, m.id LIMIT 300""")
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        if manual:
            await send(bot, "📭 Son özetten bu yana özetlenecek yeni grup e-postası yok.")
        return False

    groups = {}
    for r in rows:
        groups.setdefault(r["group_key"], {"name": r["group_name"], "items": []})["items"].append(r)

    corpus = []
    for gk, g in groups.items():
        corpus.append(f"### GRUP: {g['name']} (anahtar: {gk}) — {len(g['items'])} ileti")
        for it in g["items"][:40]:
            body = "\n".join(l for l in (it["body"] or "").splitlines() if not l.lstrip().startswith(">"))
            corpus.append(f"- [{it['sender']}] {it['subject']}: {body[:350].strip()}")
    prompt = (
        "Sen Ömer Bey'in kişisel asistanısın. Aşağıda e-posta gruplarından gelen yeni iletiler var. "
        "Her grup için Türkçe, kısa ve madde madde bir özet çıkar: hangi konular konuşuldu, öne çıkan "
        "duyurular, sorular veya Ömer Bey'i ilgilendirebilecek noktalar. Aynı konudaki iletileri birleştir. "
        "Her grup için en fazla 5 madde yaz. Ekran okuyucu ile dinleneceği için emoji ve tablo kullanma.\n"
        "Sadece şu JSON'u döndür: {\"groups\": [{\"key\": \"...\", \"bullets\": [\"...\", \"...\"]}]}\n\n"
        + "\n".join(corpus)
    )

    summaries = {}
    try:
        data = json.loads(await gemini(prompt, json_mode=True, timeout=150))
        for g in data.get("groups", []):
            summaries[g.get("key")] = [plain_ai_text(str(b)) for b in g.get("bullets", [])][:6]
    except Exception as e:
        logger.warning(f"Digest summarization failed, using subject list: {e}")

    interval = await get_setting("digest_interval_hours")
    await send(bot, f"📰 <b>Grup Özeti</b> — {len(rows)} yeni ileti, {len(groups)} grup"
                    f"{'' if manual else f' (her {interval} saatte bir)'}")
    for gk, g in groups.items():
        bullets = summaries.get(gk)
        if not bullets:  # fallback: unique subjects
            seen, bullets = set(), []
            for it in g["items"]:
                s = re.sub(r"^(re|ynt|fwd|ilt)\s*:\s*", "", it["subject"] or "", flags=re.I).strip()
                if s and s not in seen:
                    seen.add(s)
                    bullets.append(s)
            bullets = bullets[:8]
        text = f"<b>{esc(g['name'])}</b> ({len(g['items'])} ileti)\n" + "\n".join(f"• {esc(b)}" for b in bullets)
        await send(bot, text, reply_markup=group_mode_keyboard(gk, "OZET"))

    ids = [r["id"] for r in rows]
    async with database.get_db() as db:
        await db.execute(f"UPDATE group_messages SET digested=1 WHERE id IN ({','.join('?' * len(ids))})", ids)
        await db.commit()
    return True


async def build_morning_report(bot, send):
    async with database.get_db() as db:
        q = lambda sql: db.execute(sql)
        new_mails = (await (await q("SELECT COUNT(*) FROM pending_replies WHERE created_at > datetime('now','-1 day')")).fetchone())[0]
        sent = (await (await q("SELECT COUNT(*) FROM pending_replies WHERE status='SENT' AND created_at > datetime('now','-1 day')")).fetchone())[0]
        pending = (await (await q("SELECT COUNT(*) FROM pending_replies WHERE status='PENDING'")).fetchone())[0]
        grp_total = (await (await q("SELECT COUNT(*) FROM group_messages WHERE received_at > datetime('now','-1 day')")).fetchone())[0]
        cur = await q("""SELECT g.name, COUNT(*) c FROM group_messages m JOIN group_settings g ON g.group_key=m.group_key
                         WHERE m.received_at > datetime('now','-1 day') GROUP BY m.group_key ORDER BY c DESC LIMIT 5""")
        top = await cur.fetchall()
        kw = (await (await q("SELECT COUNT(*) FROM group_messages WHERE keyword_hit IS NOT NULL AND received_at > datetime('now','-1 day')")).fetchone())[0]
    lines = [
        f"☀️ <b>Günaydın Ömer Bey! Son 24 saatin raporu</b> ({datetime.now().strftime('%d.%m.%Y')})",
        "",
        f"• Kişisel e-posta: {new_mails} yeni, {sent} yanıtlandı",
        f"• Onay bekleyen taslak: {pending}" + (" (görmek için /bekleyenler)" if pending else ""),
        f"• Grup iletisi: {grp_total}",
        f"• Anahtar kelime alarmı: {kw}",
    ]
    if top:
        lines.append("")
        lines.append("<b>En hareketli gruplar:</b>")
        lines += [f"• {esc(n)}: {c} ileti" for n, c in top]
    await send(bot, "\n".join(lines))


async def run_scheduled(bot, send):
    """Called every background tick. All failures are contained."""
    try:
        await send_instant_notifications(bot, send)
    except Exception as e:
        logger.error(f"Group assistant instant job failed: {e}", exc_info=True)

    now = datetime.now()
    qs, qe = int(await get_setting("quiet_start")), int(await get_setting("quiet_end"))
    quiet = _in_quiet_hours(qs, qe, now.hour)

    # Morning report: first tick after quiet hours end
    today = now.strftime("%Y-%m-%d")
    # only within 4h after quiet hours end (never a "Günaydın" at night after an outage/deploy)
    in_window = qe <= now.hour < qe + 4
    if not quiet and in_window and await get_setting("last_morning_date") != today:
        await set_setting("last_morning_date", today)  # set first: never spam on failure
        try:
            await build_morning_report(bot, send)
        except Exception as e:
            logger.error(f"Morning report failed: {e}", exc_info=True)

    if quiet:
        return
    interval_h = float(await get_setting("digest_interval_hours"))
    last = float(await get_setting("last_digest_ts"))
    if time.time() - last >= interval_h * 3600:
        await set_setting("last_digest_ts", time.time())
        try:
            await build_and_send_digest(bot, send)
        except Exception as e:
            logger.error(f"Digest failed: {e}", exc_info=True)


# ======================= Natural language =======================
async def answer_archive(question: str, group_key: str = None, days: int = 7) -> str:
    days = max(1, min(int(days or 7), 45))
    async with database.get_db() as db:
        db.row_factory = aiosqlite.Row
        sql = ("SELECT m.sender, m.subject, m.body, m.received_at, g.name FROM group_messages m "
               "JOIN group_settings g ON g.group_key=m.group_key WHERE m.received_at > datetime('now', ?)")
        args = [f"-{days} days"]
        if group_key:
            sql += " AND m.group_key=?"
            args.append(group_key)
        sql += " ORDER BY m.id DESC LIMIT 120"
        rows = [dict(r) for r in await (await db.execute(sql, args)).fetchall()]
    if not rows:
        return "Bu aralıkta arşivde kayıtlı grup iletisi bulamadım."
    corpus = "\n".join(
        f"- ({r['received_at']}) [{r['name']}] {r['sender']} | {r['subject']}: "
        f"{' '.join(l for l in (r['body'] or '').splitlines() if not l.lstrip().startswith('>'))[:400]}"
        for r in rows)
    prompt = (f"Sen Ömer Bey'in asistanısın. Aşağıdaki grup e-postası arşivine dayanarak soruyu Türkçe, "
              f"kısa ve net yanıtla. Arşivde bilgi yoksa açıkça söyle, uydurma. Emoji kullanma.\n\n"
              f"SORU: {question}\n\nARŞİV:\n{corpus}")
    return await gemini(prompt, timeout=120)


INTENT_PROMPT = """Sen Ömer Bey'in Telegram üzerinden konuştuğu e-posta asistanısın. Kullanıcının mesajını analiz edip
yapılacak işlemi JSON olarak döndür.

MEVCUT GRUPLAR (anahtar | ad | mod | son 24 saat ileti):
{groups}

TAKİP EDİLEN ANAHTAR KELİMELER: {keywords}
AYARLAR: özet sıklığı {interval} saat, sessiz saatler {qs}:00-{qe}:00

OLASI İŞLEMLER (action):
- "set_group_mode": grup(lar)ın modunu değiştir. mode: "OZET" (özetle/arada bilgi ver), "ANLIK" (hemen at/bildir), "SESSIZ" (atma/sustur/haber verme).
- "list_groups": grupları listele
- "digest_now": şimdi özet ver
- "set_digest_interval": hours (1-24)
- "set_quiet_hours": quiet_start, quiet_end (0-23 saat)
- "add_keyword" / "remove_keyword": keyword
- "list_keywords"
- "ask_archive": grup e-postaları hakkında soru. question, isteğe bağlı group_key, days
- "morning_report": günlük raporu şimdi göster
- "pending": onay bekleyen kişisel e-posta taslakları
- "help": ne yapabildiğini sor
- "chat": yukarıdakilerin hiçbiri; kısa, nazik Türkçe cevabı "reply" alanına yaz

Grup adları kullanıcı tarafından kısaltılabilir veya farklı yazılabilir (örn. "GEÖP" -> görme engelli öğrenciler grubu,
"teknokör"). En uygun grup anahtar(lar)ını group_keys listesine koy. "tüm gruplar" denirse hepsini koy.
Emin değilsen group_keys boş bırak ve reply'da hangi grubu kastettiğini sor.

Sadece JSON döndür:
{{"action": "...", "group_keys": [], "mode": null, "hours": null, "quiet_start": null, "quiet_end": null,
  "keyword": null, "question": null, "group_key": null, "days": null, "reply": null}}

KULLANICI MESAJI: {text}"""


def _groups_text(groups: list) -> str:
    if not groups:
        return "Kayıtlı grup bulunmuyor."
    lines = []
    for g in groups:
        lines.append(f"• <b>{esc(g['name'])}</b> — {MODES.get(g['mode'], g['mode'])} — son 24 saat: {g.get('last24', 0)} ileti")
    return "\n".join(lines)


async def handle_natural_language(text: str, bot, send, pending_handler=None, help_handler=None) -> None:
    groups = await get_groups()
    keywords = await get_keywords()
    prompt = INTENT_PROMPT.format(
        groups="\n".join(f"{g['group_key']} | {g['name']} | {g['mode']} | {g.get('last24', 0)}" for g in groups) or "(henüz yok)",
        keywords=", ".join(keywords) or "(yok)",
        interval=await get_setting("digest_interval_hours"),
        qs=await get_setting("quiet_start"), qe=await get_setting("quiet_end"),
        text=text[:1500],
    )
    try:
        intent = json.loads(await gemini(prompt, json_mode=True, timeout=60, temperature=0.1))
    except Exception as e:
        logger.warning(f"Intent parsing failed: {e}")
        await send(bot, "⚠️ Şu an mesajınızı yorumlayamadım (yapay zekâ servisine ulaşılamadı). "
                        "Komutlarla devam edebilirsiniz: /gruplar, /ozet, /kelimeler, /yardim")
        return

    action = intent.get("action") or "chat"
    valid_keys = {g["group_key"]: g for g in groups}

    if action == "set_group_mode":
        mode = (intent.get("mode") or "").upper()
        keys = [k for k in (intent.get("group_keys") or []) if k in valid_keys]
        if mode not in MODES or not keys:
            await send(bot, esc(intent.get("reply") or "Hangi grubu ve nasıl ayarlamamı istediğinizi tam anlayamadım. "
                                "Grupları görmek için /gruplar yazabilirsiniz."))
            return
        for k in keys:
            await set_group_mode(k, mode)
        names = ", ".join(esc(valid_keys[k]["name"]) for k in keys)
        desc = {"OZET": f"{await get_setting('digest_interval_hours')} saatte bir özet olarak bildirilecek",
                "ANLIK": "her ileti anında bildirilecek",
                "SESSIZ": "artık bildirilmeyecek (anahtar kelime alarmları hariç), arşivlenmeye devam edecek"}[mode]
        await send(bot, f"✅ <b>{names}</b> → {MODES[mode]}\nBu gruptan gelenler {desc}.")
    elif action == "list_groups":
        await send(bot, "📚 <b>Takip edilen gruplar</b>\n\n" + _groups_text(groups) +
                        "\n\nDeğiştirmek için /gruplar yazın veya örneğin “GEÖP'ü sustur” deyin.")
    elif action == "digest_now":
        await build_and_send_digest(bot, send, manual=True)
    elif action == "set_digest_interval":
        h = intent.get("hours")
        try:
            h = max(1, min(24, int(float(h))))
        except Exception:
            await send(bot, "Kaç saatte bir özet istediğinizi anlayamadım (1-24 arası).")
            return
        await set_setting("digest_interval_hours", h)
        await send(bot, f"✅ Grup özetleri artık <b>{h} saatte bir</b> gönderilecek.")
    elif action == "set_quiet_hours":
        try:
            s, e = int(intent.get("quiet_start")) % 24, int(intent.get("quiet_end")) % 24
        except Exception:
            await send(bot, "Sessiz saat aralığını anlayamadım. Örnek: “sessiz saatler 23 ile 9 arası olsun”.")
            return
        await set_setting("quiet_start", s)
        await set_setting("quiet_end", e)
        await send(bot, f"✅ Sessiz saatler: <b>{s:02d}:00 – {e:02d}:00</b>. Bu aralıkta özet gönderilmez, sabah toplu gelir.")
    elif action == "add_keyword" and intent.get("keyword"):
        kw = str(intent["keyword"]).strip()[:60]
        ok = await add_keyword(kw)
        await send(bot, f"✅ “{esc(kw)}” takibe alındı. Herhangi bir grupta geçerse (sessizdeki gruplar dahil) anında haber vereceğim."
                        if ok else f"ℹ️ “{esc(kw)}” zaten takip ediliyor.")
    elif action == "remove_keyword" and intent.get("keyword"):
        ok = await remove_keyword(str(intent["keyword"]))
        await send(bot, f"✅ “{esc(intent['keyword'])}” takipten çıkarıldı." if ok
                   else f"ℹ️ “{esc(intent['keyword'])}” takip listesinde yok. Liste için /kelimeler")
    elif action == "list_keywords":
        await send(bot, "🔔 <b>Takip edilen anahtar kelimeler</b>\n" + "\n".join(f"• {esc(k)}" for k in keywords))
    elif action == "ask_archive":
        gk = intent.get("group_key") if intent.get("group_key") in valid_keys else None
        await send(bot, "🔍 <i>Arşive bakıyorum...</i>")
        try:
            ans = await answer_archive(intent.get("question") or text, gk, intent.get("days") or 7)
        except Exception as e:
            ans = f"Arşiv sorgusu başarısız oldu: {e}"
        await send(bot, f"🔍 {esc(plain_ai_text(ans))}")
    elif action == "morning_report":
        await build_morning_report(bot, send)
    elif action == "pending" and pending_handler:
        await pending_handler()
    elif action == "help" and help_handler:
        await help_handler()
    else:
        await send(bot, esc(intent.get("reply") or "Anlayamadım. /yardim yazarak neler yapabildiğimi görebilirsiniz."))
