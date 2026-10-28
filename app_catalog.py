import sqlite3
import os
import time
import logging
import config

logger = logging.getLogger(__name__)

APPS_DB_PATH = getattr(config, "APPS_DB_PATH", "/var/www/apps.omergoktas.net/data/apps.sqlite")
SHOWCASE_BASE_URL = getattr(config, "SHOWCASE_BASE_URL", "https://apps.omergoktas.net")

_cached_apps = None
_cached_time = 0
CACHE_TTL = 30  # 30 seconds cache for instant reflection of admin panel updates

def get_published_apps(force_refresh: bool = False):
    global _cached_apps, _cached_time
    now = time.time()
    if not force_refresh and _cached_apps is not None and (now - _cached_time < CACHE_TTL):
        return _cached_apps

    if not os.path.exists(APPS_DB_PATH):
        logger.warning(f"Apps database not found at {APPS_DB_PATH}")
        return []

    try:
        conn = sqlite3.connect(f"file:{APPS_DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT a.id, a.title, a.slug, a.version, c.name as category_name, a.platforms,
                   a.short_summary, a.description, a.google_play_url, a.microsoft_store_url,
                   a.github_url, a.direct_download_url, a.is_published
            FROM apps a
            LEFT JOIN categories c ON a.category_id = c.id
            WHERE a.is_published = 1
            ORDER BY a.sort_order ASC, a.id ASC
        """)
        rows = cur.fetchall()
        apps = []
        for r in rows:
            d = dict(r)
            d["showcase_url"] = f"{SHOWCASE_BASE_URL}/app/{d['slug']}" if d.get("slug") else SHOWCASE_BASE_URL
            apps.append(d)
        conn.close()
        _cached_apps = apps
        _cached_time = now
        return apps
    except Exception as e:
        logger.error(f"Error reading apps database: {e}")
        return _cached_apps or []

def get_catalog_prompt_context() -> str:
    apps = get_published_apps()
    if not apps:
        return f"Ömer Göktaş Uygulamaları Vitrin Sitesi: {SHOWCASE_BASE_URL}\nŞu anda vitrinde listelenen aktif uygulama bulunmuyor."

    lines = [
        f"ÖMER GÖKTAŞ UYGULAMALARI VİTRİN SİTESİ: {SHOWCASE_BASE_URL}",
        "VİTRİNDE YAYINDA OLAN GÜNCEL UYGULAMALAR VE RESMİ İNDİRME/MAĞAZA BAĞLANTILARI:"
    ]
    for idx, a in enumerate(apps, 1):
        links = []
        if a.get("google_play_url"):
            links.append(f"Google Play: {a['google_play_url']}")
        if a.get("microsoft_store_url"):
            links.append(f"Microsoft Store: {a['microsoft_store_url']}")
        if a.get("github_url"):
            links.append(f"GitHub: {a['github_url']}")
        if a.get("direct_download_url"):
            links.append(f"Doğrudan İndirme: {a['direct_download_url']}")
        links.append(f"Vitrin Detay Sayfası: {a['showcase_url']}")

        links_str = "\n      * " + "\n      * ".join(links)
        summary = (a.get("short_summary") or "").strip()
        lines.append(
            f"[{idx}] {a['title']} (Sürüm: {a.get('version', 'Güncel')}, Platform: {a.get('platforms', 'Belirtilmemiş')}, Kategori: {a.get('category_name', 'Genel')})\n"
            f"   - Açıklama: {summary}\n"
            f"   - Resmi Bağlantılar:{links_str}"
        )
    return "\n\n".join(lines)