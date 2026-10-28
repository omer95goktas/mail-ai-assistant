# 🤖 Otonom AI E-posta Asistanı (MailAgent)

Çoklu e-posta hesap destekli, SQLite tabanlı, Google Gemini yapay zeka entegrasyonlu ve Telegram üzerinden tam kontrollü otonom e-posta yönetim servisi.

Bu asistan; **Ömer Göktaş** adına *"Paylaşılmayan bilgi, bilgi değildir"* vizyonuyla gelen e-postaları inceler, özetler, yanıt taslakları hazırlar ve vitrin sitesi (**[apps.omergoktas.net](https://apps.omergoktas.net)**) ile entegre biçimde otonom olarak çalışır.

---

## 🌟 Temel Özellikler

1. **Çoklu E-posta Hesap Desteği (Multi-Account):**
   - SQLite veritabanında saklanan bağımsız IMAP/SMTP hesapları.
   - Her hesap için bağımsız yoklama (polling), okuma ve gönderme yeteneği.
   - Telegram üzerinden adım adım etkileşimli hesap ekleme, silme ve durum değiştirme sihirbazı.

2. **Google Gemini AI Entegrasyonu:**
   - E-posta içeriği, gönderen ve konu başlığını anlık analiz eder.
   - *Ömer Göktaş* persona kurallarına uygun, nazik, net, profesyonel ve paylaşımcı yanıt taslakları üretir.

3. **apps.omergoktas.net Vitrin Sitesi ile Canlı Entegrasyon:**
   - Sunucudaki vitrin SQLite veritabanına (`apps.sqlite`) kilitlenmesiz (*Read-Only*) modda bağlanır.
   - Yayında olan tüm güncel uygulamaları (Engelsiz Android, Erişilebilir Kitap Okuyucu, Medya İşleme Merkezi vb.) ve resmi mağaza/indirme bağlantılarını dinamik olarak tanır.

4. **⚡ Akıllı Otonom Yanıtlama (Auto-Reply):**
   - E-posta herhangi bir uygulamanın mağaza/indirme linkini veya vitrin adresini soruyorsa onay beklemeden doğrudan yanıtlar, IMAP üzerinde okundu (`\Seen`) işaretler ve Telegram'a rapor iletir.
   - İş birliği, teknik hata veya karmaşık konularda ise Telegram onay akışını devreye sokar.

5. **🎛️ Gelişmiş Telegram Onay Kontrolleri:**
   - **`[✅ Gönder]`**: Onaylanan yanıtı SMTP üzerinden (RFC uyumlu `In-Reply-To` ve `References` başlıklarıyla) güvenle iletir.
   - **`[🔄 Farklı Yanıt Üret]`**: Mevcut taslağı farklı bir ton ve yaklaşımla Gemini'ye yeniden yazdırır.
   - **`[✍️ Talimatla Düzenle]`**: Kullanıcının Telegram'dan yazdığı özel nota göre taslağı anında yeniden şekillendirir.
   - **`[❌ İptal]`**: Yanıtı iptal eder.

6. **🛡️ Mailing List & Grup Filtresi (Ignore Filter):**
   - Google Groups, Yahoo Groups, toplu bültenler (`List-Id`, `Precedence: bulk/list`) ve `no-reply` maillerini otomatik filtreleyerek kota tüketimini ve sonsuz döngüleri engeller.

7. **Debian Linux Systemd Servisi:**
   - `mailagent.service` ile 7/24 arka planda kesintisiz ve hataya dayanıklı (auto-restart) çalışma.

---

## 📁 Proje Dizin Yapısı

```text
/opt/mail_assistant/
├── .env                      # Ortam değişkenleri ve gizli anahtarlar (Git dışı)
├── .env.example              # Örnek ortam değişkenleri şablonu
├── .gitignore                # Hassas verileri ve sanal ortamı hariç tutma kuralları
├── requirements.txt          # Python kütüphane bağımlılıkları
├── config.py                 # Yapılandırma ve parametre yükleyici
├── database.py               # SQLite veritabanı CRUD işlemleri (aiosqlite)
├── app_catalog.py            # Vitrin sitesi SQLite veritabanı okuyucusu
├── ai_service.py             # Google Gemini AI analiz ve taslak üretim servisi
├── mail_service.py           # IMAP e-posta dinleme ve SMTP gönderim motoru
├── bot.py                    # Telegram botu komutları ve callback yöneticisi
├── main.py                   # Uygulama ana giriş noktası ve asenkron döngü
├── mailagent.service         # Systemd servis tanım dosyası
└── data/
    └── assistant.db          # Asistan SQLite veritabanı (Otomatik oluşturulur)
```

---

## 🚀 Kurulum Rehberi (Debian / Ubuntu)

### 1. Sistem Bağımlılıklarının Yüklenmesi
```bash
sudo apt update && sudo apt install -y python3 python3-venv git
```

### 2. Proje Dizinine Geçiş ve Sanal Ortam (venv) Kurulumu
```bash
sudo mkdir -p /opt/mail_assistant
cd /opt/mail_assistant
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Ortam Değişkenlerinin (.env) Ayarlanması
`.env.example` dosyasını kopyalayarak `.env` dosyanızı oluşturun:
```bash
cp .env.example .env
chmod 600 .env
nano .env
```

`.env` dosyasındaki değerleri kendi bilgilerinize göre doldurun:
```ini
TELEGRAM_BOT_TOKEN="BOTFATHER_TOKEN"
TELEGRAM_ADMIN_CHAT_ID="YONETICI_CHAT_ID"
GEMINI_API_KEY="GOOGLE_AI_STUDIO_API_KEY"
GEMINI_MODEL="gemini-3.5-flash"
DB_PATH="/opt/mail_assistant/data/assistant.db"
CHECK_INTERVAL="60"
APPS_DB_PATH="/var/www/apps.omergoktas.net/data/apps.sqlite"
SHOWCASE_BASE_URL="https://apps.omergoktas.net"
```

### 4. Systemd Servisinin Yapılandırılması ve Başlatılması
Servis dosyasını systemd dizinine kopyalayın:
```bash
sudo cp mailagent.service /etc/systemd/system/mailagent.service
sudo systemctl daemon-reload
sudo systemctl enable mailagent.service
sudo systemctl restart mailagent.service
```

Servis durumunu kontrol edin:
```bash
sudo systemctl status mailagent.service
```

Canlı logları takip etmek için:
```bash
journalctl -u mailagent.service -f
```

---

## 📱 Telegram Komut Kılavuzu

| Komut | Açıklama |
| :--- | :--- |
| `/start` veya `/yardim` | Bot durumunu ve detaylı komut kılavuzunu görüntüler. |
| `/hesaplar` | Kayıtlı tüm e-posta hesaplarını ve aktiflik durumlarını listeler. |
| `/hesap_ekle` | Adım adım yeni hesap ekleme sihirbazını başlatır. |
| `/hesap_sil <id>` | Belirtilen hesabı veritabanından siler. |
| `/vitrin` | `apps.omergoktas.net` üzerinde yayında olan güncel uygulamaları listeler. |
| `/durum` | Sunucu kaynak kullanımı (CPU/RAM/Disk), veritabanı boyutu ve onay istatistiklerini raporlar. |
| `/kontrol_et` | Periyodik döngüyü beklemeden hesapları anında manuel olarak taratır. |
| `/iptal` | Devam eden hesap ekleme veya taslak düzenleme sihirbazını iptal eder. |

---

## 🗄️ Veritabanı Şeması (SQLite)

### `accounts` Tablosu
| Sütun | Tip | Açıklama |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Hesap benzersiz kimliği |
| `email_address` | TEXT UNIQUE | E-posta adresi |
| `imap_server` | TEXT | IMAP sunucu adresi (Örn: imap.gmail.com) |
| `imap_port` | INTEGER | IMAP portu (Varsayılan: 993) |
| `smtp_server` | TEXT | SMTP sunucu adresi (Örn: smtp.gmail.com) |
| `smtp_port` | INTEGER | SMTP portu (Varsayılan: 587) |
| `app_password` | TEXT | Uygulama şifresi |
| `is_active` | INTEGER | Aktiflik durumu (1: Aktif, 0: Pasif) |
| `check_interval_seconds` | INTEGER | Tarama periyodu (saniye) |

### `pending_replies` Tablosu
| Sütun | Tip | Açıklama |
| :--- | :--- | :--- |
| `id` | INTEGER PRIMARY KEY | Yanıt işlem kimliği |
| `account_id` | INTEGER | İlgili hesabın referans ID'si |
| `message_id` | TEXT | Orijinal e-postanın `Message-ID` başlığı |
| `sender` | TEXT | Gönderen kişi ve adresi |
| `subject` | TEXT | E-posta konusu |
| `incoming_snippet` | TEXT | Gelen mesajın gövde metni |
| `gemini_summary` | TEXT | Gemini tarafından üretilen özet |
| `draft_reply` | TEXT | Önerilen / düzenlenen yanıt taslağı |
| `status` | TEXT | Durum (`PENDING`, `SENT`, `CANCELLED`) |

---

## 🔒 Güvenlik Notları
- `.env` dosyası ve SQLite veritabanı dosyaları `.gitignore` kapsamında olup **asla sürüm kontrolüne (Git) gönderilmez**.
- Telegram botu yalnızca `TELEGRAM_ADMIN_CHAT_ID` ile yetkilendirilmiş yöneticiye cevap verir, yabancı kullanıcıların tüm istekleri reddedilir.
- IMAP ve SMTP bağlantıları TLS/SSL şifreli kanallar üzerinden gerçekleştirilir.