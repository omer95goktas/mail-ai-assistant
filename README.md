# Yapay Zekâ E-posta Asistanı (Telegram + Gemini)

Gelen e-postalarınızı sizin yerinize okuyan, özetleyen, yanıt taslağı hazırlayan ve her şeyi
**Telegram** üzerinden onayınıza sunan kişisel bir e-posta asistanı.
Yanıtları Google **Gemini** yapay zekâsı hazırlar; **hiçbir e-posta sizin onayınız olmadan gönderilmez**
(isteğe bağlı katalog özelliği hariç, aşağıya bakın).

Bot tamamen Türkçedir ve ekran okuyucu kullanıcıları düşünülerek tasarlanmıştır.

> Kurulum için adım adım anlatım: **[KURULUM.md](KURULUM.md)**

---

## Neler yapar?

### 1. Kişisel e-postalar
Yeni bir e-posta geldiğinde Telegram'a şu bilgiler gelir: kimden geldiği, konusu, kısa özeti ve
Gemini'nin hazırladığı yanıt taslağı. Mesajın altında dört buton bulunur:

- **✅ Onayla**: Taslağı karşı tarafa gönderir.
- **✍️ Kendim Yaz**: Sizin yazacağınız metni gönderir.
- **🔄 Yeniden Üret**: Farklı bir üslupla yeni taslak hazırlar.
- **👁️ Okundu Yap**: Yanıt göndermeden kapatır.

Asistan, karşı tarafa kendini açıkça **"(Sizin adınız)'ın yapay zekâ asistanı"** olarak tanıtır ve her yanıta
sizin denetiminizde çalıştığını belirten bir şeffaflık notu ekler. Ad, hitap ve imza ayarlardan değiştirilebilir.

### 2. Grup e-postaları (Google Grupları, groups.io vb.)
Grup e-postaları gelen kutunuzda okundu olarak işaretlenir ve sizi rahatsız etmez; asistan bunları arşivler
ve size haber verir. Her grup için üç mod vardır:

- **📰 Özet** (varsayılan): Birkaç saatte bir, konuşulanların madde madde özeti gelir.
- **⚡ Anlık**: O gruptan gelen her ileti hemen size iletilir.
- **🔕 Sessiz**: Hiç bildirim gelmez, yalnızca arşivlenir.

### 3. Asistanla normal cümlelerle konuşma
Komut ezberlemeniz gerekmez. Bota şöyle yazabilirsiniz:

- "Duyurular grubundan bana mail atma"
- "Destek grubundan gelenleri hemen bildir"
- "Hangi gruplardan mail geliyor?"
- "Şimdi bir özet ver"
- "Özetleri 6 saatte bir gönder"
- "Sessiz saatler 23 ile 9 arası olsun"
- "Proje adımı da takip et: Örnek Uygulama"
- "Dün destek grubunda hangi sorunlar konuşuldu?"

### 4. Diğer özellikler
- **🔔 Anahtar kelime alarmı:** Adınız (veya eklediğiniz kelimeler) herhangi bir grupta geçerse, grup sessizde olsa bile anında haber verir.
- **🌙 Sessiz saatler:** Varsayılan olarak 00:00–08:00 arası özet gönderilmez; birikenler sabah gelir.
- **☀️ Sabah raporu:** Her sabah son 24 saatin özeti.
- **🔍 Arşivde soru:** Grup e-postaları hakkında soru sorabilirsiniz.
- **📦 Uygulama kataloğu (isteğe bağlı):** Uygulama geliştiriyorsanız, "X uygulamasının indirme linki nedir?" gibi e-postalara doğru bağlantılarla otomatik yanıt verilebilir.

### 5. Güvenilirlik
- E-postalar önce kalıcı bir kuyruğa yazılır, ancak ondan sonra okundu işaretlenir; çökme veya bağlantı kopması durumunda **e-posta kaybolmaz**.
- Çift tıklamada aynı e-posta iki kez gönderilmez.
- Bağımsız bir **bekçi (watchdog)** her 3 dakikada bir servisi kontrol eder; donar veya çökerse yeniden başlatır ve sizi bilgilendirir.
- Veritabanının günlük yedeği alınır (son 7 gün saklanır).
- E-posta sunucusuna uzun süre ulaşılamazsa (örneğin şifre değiştiyse) size uyarı gelir.

---

## Gereksinimler

- Sürekli açık bir **Linux sunucu** (Debian 12 / Ubuntu 22.04 veya üstü önerilir; küçük bir VPS yeterlidir)
- **Python 3.10** veya üstü
- Bir **Telegram** hesabı
- Ücretsiz bir **Gemini API anahtarı** (Google AI Studio)
- IMAP/SMTP destekleyen bir e-posta hesabı (Gmail, Google Workspace, Outlook, Yandex vb.) ve **uygulama şifresi**

## Hızlı kurulum (özet)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv
sudo git clone <BU_REPONUN_ADRESİ> /opt/mail_assistant
cd /opt/mail_assistant
sudo bash install.sh          # ilk çalıştırmada .env dosyasını oluşturur
sudo nano .env                # bilgilerinizi girin
sudo bash install.sh          # kurulumu tamamlar ve servisi başlatır
```

Ardından Telegram'da botunuza `/start`, sonra `/hesap_ekle` yazın.
Her adımın ayrıntılı açıklaması **[KURULUM.md](KURULUM.md)** dosyasındadır.

---

## Telegram komutları

| Komut | Açıklama |
|---|---|
| `/yardim` | Tüm özellikler ve örnek cümleler |
| `/bekleyenler` | Onay bekleyen yanıt taslakları |
| `/gruplar` | Gruplar ve bildirim modları (butonlu) |
| `/ozet` | Grup özetini hemen gönder |
| `/kelimeler` | Takip edilen anahtar kelimeler |
| `/rapor` | Günlük raporu hemen göster |
| `/kontrol_et` | Gelen kutusunu hemen tara |
| `/durum` | Sistem durumu |
| `/hesap_ekle` | Yeni e-posta hesabı ekle (sihirbaz) |
| `/hesaplar` | Kayıtlı e-posta hesapları |
| `/hesap_sil <id>` | Hesap sil |
| `/iptaller` | İptal edilen yanıtlar (`/geri_al <id>` ile geri alınır) |
| `/vitrin` | Uygulama kataloğu (tanımlıysa) |
| `/iptal` | Yazma / düzenleme modundan çık |

Taslaklar için hızlı yazılı komutlar: `gönder`, `okundu yap`, `yeniden üret` (en son bekleyen taslağa uygulanır).

---

## Proje yapısı

```
main.py              Uygulamanın giriş noktası, arka plan döngüsü
bot.py               Telegram komutları, butonlar, e-posta işleme döngüsü
mail_service.py      IMAP okuma, SMTP gönderme, HTML imza
ai_service.py        Gemini ile özet ve yanıt taslağı üretimi
group_assistant.py   Grup özetleri, modlar, anahtar kelimeler, doğal dil
database.py          SQLite veritabanı ve kalıcı kuyruk
app_catalog.py       İsteğe bağlı uygulama kataloğu
config.py            Ayarların .env dosyasından okunması
watchdog.py          Bağımsız bekçi + günlük yedek
install.sh           Kurulum betiği
mailagent.service    systemd servis şablonu
.env.example         Örnek ayar dosyası
catalog.example.json Örnek katalog dosyası
```

## Gizlilik

- Tüm veriler (hesap bilgileri, taslaklar, grup arşivi) **yalnızca sizin sunucunuzda**, yerel bir SQLite dosyasında tutulur.
- E-posta içerikleri özet ve taslak üretmek için Google Gemini API'sine gönderilir.
- Bot yalnızca `.env` dosyasında tanımlı Telegram kullanıcısına yanıt verir; başkaları kullanamaz.
- `.env` dosyanızı ve `data/` klasörünü asla paylaşmayın.
