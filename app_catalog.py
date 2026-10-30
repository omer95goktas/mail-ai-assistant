"""
Uygulama kataloğu (isteğe bağlı).

Katalog tanımlıysa asistan, "X uygulamasının indirme linki nedir?" gibi e-postalara
doğru bağlantılarla (gerekirse otomatik) yanıt verir. İki kaynak desteklenir:

1) CATALOG_JSON_PATH  -> basit JSON dosyası (bkz. catalog.example.json)
2) APPS_DB_PATH       -> uyumlu şemaya sahip SQLite veritabanı (salt okunur)

Hiçbiri tanımlı değilse katalog özellikleri sessizce devre dışı kalır.
"""
import os
import json
import time
import sqlite3
import logging
import config

logger = logging.getLogger(__name__)

CACHE_TTL = 30
_cached_apps = None
_cached_time = 0.0

LINK_FIELDS = [
    ("google_play_url", "Google Play"),
    ("microsoft_store_url", "Microsoft Store"),
    ("app_store_url", "App Store"),
    ("github_url", "GitHub"),
    ("direct_download_url", "Doğrudan İndirme"),
]


def has_catalog() -> bool:
    return bool(
        (config.CATALOG_JSON_PATH and os.path.exists(config.CATALOG_JSON_PATH))
        or (config.APPS_DB_PATH and os.path.exists(config.APPS_DB_PATH))
    )


def _detail_url(slug: str) -> str:
    base = (config.CATALOG_SITE_URL or "").rstrip("/")
    if base and slug:
        return f"{base}/app/{slug}"
    return base


def _load_json() -> list:
    with open(config.CATALOG_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("apps", []) if isinstance(data, dict) else data
    apps = []
    for a in items:
        if not a.get("title") or a.get("published", True) is False:
            continue
        a = dict(a)
        a.setdefault("short_summary", a.get("summary", ""))
        a["showcase_url"] = a.get("detail_url") or _detail_url(a.get("slug", ""))
        apps.append(a)
    return apps


def _load_sqlite() -> list:
    conn = sqlite3.connect(f"file:{config.APPS_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT a.id, a.title, a.slug, a.version, c.name AS category_name, a.platforms,
                   a.short_summary, a.description, a.google_play_url, a.microsoft_store_url,
                   a.github_url, a.direct_download_url, a.is_published
            FROM apps a LEFT JOIN categories c ON a.category_id = c.id
            WHERE a.is_published = 1
            ORDER BY a.sort_order ASC, a.id ASC
        """).fetchall()
    finally:
        conn.close()
    apps = []
    for r in rows:
        d = dict(r)
        d["showcase_url"] = _detail_url(d.get("slug"))
        apps.append(d)
    return apps


def get_published_apps(force_refresh: bool = False) -> list:
    global _cached_apps, _cached_time
    now = time.time()
    if not force_refresh and _cached_apps is not None and now - _cached_time < CACHE_TTL:
        return _cached_apps
    if not has_catalog():
        return []
    try:
        if config.CATALOG_JSON_PATH and os.path.exists(config.CATALOG_JSON_PATH):
            apps = _load_json()
        else:
            apps = _load_sqlite()
        _cached_apps, _cached_time = apps, now
        return apps
    except Exception as e:
        logger.error(f"Katalog okunamadı: {e}")
        return _cached_apps or []


def get_catalog_prompt_context() -> str:
    apps = get_published_apps()
    site = config.CATALOG_SITE_URL
    if not apps:
        return (f"Katalog sitesi: {site}\n" if site else "") + "Katalogda listelenen aktif uygulama bulunmuyor."

    lines = []
    if site:
        lines.append(f"KATALOG SİTESİ: {site}")
    lines.append("KATALOGDAKİ UYGULAMALAR VE RESMİ BAĞLANTILARI:")
    for idx, a in enumerate(apps, 1):
        links = [f"{label}: {a[key]}" for key, label in LINK_FIELDS if a.get(key)]
        if a.get("showcase_url"):
            links.append(f"Detay Sayfası: {a['showcase_url']}")
        links_str = ("\n      * " + "\n      * ".join(links)) if links else " (bağlantı yok)"
        lines.append(
            f"[{idx}] {a['title']} (Sürüm: {a.get('version') or 'Güncel'}, "
            f"Platform: {a.get('platforms') or 'Belirtilmemiş'}, Kategori: {a.get('category_name') or 'Genel'})\n"
            f"   - Açıklama: {(a.get('short_summary') or '').strip()}\n"
            f"   - Resmi Bağlantılar:{links_str}"
        )
    return "\n\n".join(lines)
