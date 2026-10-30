# Kurulum Kılavuzu

> Bu bot **Ömer Göktaş** tarafından geliştirilmiştir.
> Soru, öneri ve geri bildirimleriniz için: **mail@omergoktas.net**

Bu kılavuz, asistanı **hiç bilmeyen birinin** de kurabilmesi için adım adım yazılmıştır.
Toplam süre yaklaşık 20–30 dakikadır. Adımları sırayla izleyin.

İçindekiler:

1. Başlamadan önce neler gerekiyor?
2. Telegram botu oluşturma
3. Telegram kullanıcı numaranızı öğrenme
4. Gemini API anahtarı alma
5. E-posta uygulama şifresi oluşturma
6. Sunucuya kurulum
7. Ayar dosyasını (.env) doldurma
8. Kurulumu tamamlama
9. E-posta hesabını ekleme
10. İlk kullanım
11. Uygulama kataloğu (isteğe bağlı)
12. Güncelleme, durdurma ve kaldırma
13. Sorun giderme
14. Geliştirici ve iletişim

---

## 1. Başlamadan önce neler gerekiyor?

- **Linux sunucu:** Asistanın 7/24 çalışabilmesi için sürekli açık bir bilgisayar gerekir. En kolayı aylık
  birkaç dolarlık bir VPS kiralamaktır (Hetzner, DigitalOcean, Contabo, yerli sağlayıcılar vb.).
  Debian 12 veya Ubuntu 22.04/24.04 seçin. 1 GB RAM yeterlidir.
- Sunucuya **SSH** ile bağlanabilmek (Windows'ta "Terminal" veya PuTTY, macOS/Linux'ta "Terminal").
- Bir **Telegram** hesabı.
- Bir **Google hesabı** (Gemini API anahtarı için).
- Asistanın okuyacağı **e-posta hesabı**.

Aşağıdaki adımlarda üç bilgi toplayacaksınız. Bir not defterine kaydedin:

1. Telegram bot anahtarı (token)
2. Telegram kullanıcı numaranız
3. Gemini API anahtarı

ve e-posta hesabınız için bir **uygulama şifresi**.

---

## 2. Telegram botu oluşturma

1. Telegram'da arama kısmına **@BotFather** yazın ve mavi tikli resmi hesabı açın.
2. **/newbot** yazıp gönderin.
3. Botunuza bir **görünen ad** verin (örnek: `Ayşe'nin E-posta Asistanı`).
4. Bir **kullanıcı adı** verin. Sonu `bot` ile bitmelidir ve benzersiz olmalıdır
   (örnek: `ayse_eposta_bot`).
5. BotFather size şuna benzer bir **token** verir:
   `7123456789:AAHk3x...uzun-bir-metin`
   Bunu not alın. **Bu anahtarı kimseyle paylaşmayın**; elinde olan herkes botunuzu yönetebilir.

---

## 3. Telegram kullanıcı numaranızı öğrenme

Bot yalnızca sizin mesajlarınıza yanıt verecek; bunun için kullanıcı numaranız gerekiyor.

1. Telegram'da **@userinfobot** hesabını açın.
2. **/start** yazın.
3. Size gelen mesajdaki **Id** değerini (örnek: `123456789`) not alın.

---

## 4. Gemini API anahtarı alma

1. Tarayıcıda **https://aistudio.google.com/apikey** adresine gidin ve Google hesabınızla giriş yapın.
2. **"Create API key"** (API anahtarı oluştur) düğmesine basın.
3. Oluşan anahtarı (genellikle `AIza` ile başlar) kopyalayıp not alın.

Ücretsiz kullanım kotası kişisel kullanım için genellikle yeterlidir.

---

## 5. E-posta uygulama şifresi oluşturma

Güvenlik nedeniyle asistan normal şifrenizi değil, yalnızca bu iş için üretilmiş bir **uygulama şifresi** kullanır.

### Gmail veya Google Workspace

1. Google hesabınızda **2 Adımlı Doğrulama** açık olmalıdır:
   https://myaccount.google.com/security → "2 Adımlı Doğrulama".
2. Ardından **https://myaccount.google.com/apppasswords** adresine gidin.
3. Uygulama adı olarak `E-posta Asistanı` yazıp **Oluştur**'a basın.
4. Size gösterilen **16 haneli şifreyi** not alın (boşluklar önemli değil).
5. Gmail'de IMAP genellikle açıktır. Kapalıysa: Gmail → Ayarlar → Tüm ayarları göster →
   "Yönlendirme ve POP/IMAP" → **IMAP'yi etkinleştir**.

> Google Workspace (şirket hesabı) kullanıyorsanız, yöneticinin uygulama şifrelerine izin vermesi gerekebilir.

### Outlook / Hotmail

Microsoft hesabınızda iki adımlı doğrulamayı açın, ardından
https://account.microsoft.com/security → "Gelişmiş güvenlik seçenekleri" → **Uygulama parolası oluştur**.

### Yandex

Yandex ID → Güvenlik → **Uygulama şifreleri** → "Posta" için şifre oluşturun.
Yandex Mail ayarlarından IMAP erişimini açmayı unutmayın.

---

## 6. Sunucuya kurulum

Sunucunuza SSH ile bağlanın (sağlayıcınızın verdiği IP adresi ve şifreyle):

```bash
ssh root@SUNUCU_IP_ADRESI
```

Gerekli araçları kurun ve projeyi indirin:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv nano
sudo git clone <BU_REPONUN_ADRESİ> /opt/mail_assistant
cd /opt/mail_assistant
```

Kurulum betiğini ilk kez çalıştırın:

```bash
sudo bash install.sh
```

Betik Python paketlerini kurar, sizin için bir **.env** ayar dosyası oluşturur ve durur.
Bu normaldir; sıradaki adımda bu dosyayı dolduracaksınız.

---

## 7. Ayar dosyasını (.env) doldurma

Dosyayı açın:

```bash
sudo nano /opt/mail_assistant/.env
```

Ok tuşlarıyla gezinip tırnak içindeki örnek değerleri kendi bilgilerinizle değiştirin.

**Zorunlu alanlar:**

| Ayar | Ne yazılacak |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 2. adımdaki bot anahtarı |
| `TELEGRAM_ADMIN_CHAT_ID` | 3. adımdaki kullanıcı numarası (yalnızca rakam) |
| `GEMINI_API_KEY` | 4. adımdaki API anahtarı |

**Kimlik alanları** (asistan sizin adınıza nasıl konuşacak):

| Ayar | Örnek |
|---|---|
| `OWNER_FULL_NAME` | `Ayşe Yılmaz` |
| `OWNER_ADDRESS` | `Ayşe Hanım` |
| `OWNER_ADDRESS_POSSESSIVE` | `Ayşe Hanım'ın` |
| `MAIL_FROM_NAME` | `Ayşe Yılmaz` |
| `ASSISTANT_SIGNATURE_NAME` | `Gemini (Ayşe Yılmaz Asistanı)` |
| `SIGNATURE_URL` | Web siteniz varsa adresi, yoksa boş bırakın |

> **Neden iyelik hali ayrı yazılıyor?** Türkçede ek, ismin son harfine göre değişir
> ("Ayşe Hanım'ın", "Mehmet Bey'in", "Dr. Can'ın", "Elif Öğretmen'in"). Bunu programın tahmin etmesi
> hatalı sonuç verebileceği için doğru hâlini sizin yazmanız istenir.

Bu ayarlarla karşı tarafa giden bir yanıt şöyle görünür:

```
Merhaba Mehmet Bey,

Ben Ayşe Hanım'ın yapay zekâ asistanıyım. ...

Bu yanıt Ayşe Hanım'ın kontrolü ve onayı doğrultusunda hazırlanmıştır. Sistemdeki her işlem
Ayşe Hanım'ın denetimindedir ve gerekli durumlarda kendisi doğrudan iletişime geçecektir.

Saygılarımla,
Gemini (Ayşe Yılmaz Asistanı)
Onaylayan: Ayşe Yılmaz
```

Diğer ayarları varsayılan haliyle bırakabilirsiniz.

Kaydetmek için **Ctrl + O**, ardından **Enter**; çıkmak için **Ctrl + X**.

---

## 8. Kurulumu tamamlama

Betiği tekrar çalıştırın:

```bash
sudo bash install.sh
```

Betik şunları yapar:

1. Ayarlarınızı kontrol eder; eksik varsa hangisi olduğunu söyler.
2. Telegram botuna ve Gemini'ye bağlanmayı dener.
3. Asistanı bir **sistem servisi** olarak kurar ve başlatır. Sunucu yeniden başlasa bile asistan kendiliğinden açılır.
4. **Bekçiyi** kurar: Her 3 dakikada bir asistanın çalıştığını kontrol eder.

Sonunda **"KURULUM TAMAMLANDI!"** yazısını görmelisiniz. Aynı anda Telegram'a da
"Asistan başlatıldı" mesajı gelir.

---

## 9. E-posta hesabını ekleme

Telegram'da botunuzu açın (BotFather'ın verdiği bağlantıdan veya kullanıcı adını aratarak):

1. **/start** yazın. Yardım sayfası gelir.
2. **/hesap_ekle** yazın ve soruları yanıtlayın:
   - **E-posta adresi:** örnek `ayse@gmail.com`
   - **IMAP sunucusu:** Bot, adresinize göre doğru değeri önerir. Önerilen değeri kullanmak için
     **varsayilan** yazmanız yeterlidir.
   - **SMTP sunucusu:** Yine **varsayilan** yazabilirsiniz.
   - **Uygulama şifresi:** 5. adımda oluşturduğunuz 16 haneli şifre.
     Güvenliğiniz için bot, şifrenin yazıldığı mesajı **otomatik olarak siler**.
3. Bot bağlantıyı test eder ve **"Hesap başarıyla eklendi"** der.

Bilinen sunucu ayarları:

| Sağlayıcı | IMAP | SMTP |
|---|---|---|
| Gmail / Google Workspace | `imap.gmail.com:993` | `smtp.gmail.com:587` |
| Outlook / Hotmail | `outlook.office365.com:993` | `smtp.office365.com:587` |
| Yandex | `imap.yandex.com:993` | `smtp.yandex.com:465` |

> Asistan yalnızca **hesabı eklediğiniz günden itibaren** gelen okunmamış e-postaları işler.
> Gelen kutunuzdaki eski okunmamış e-postalara dokunmaz.

---

## 10. İlk kullanım

- Kendinize başka bir adresten bir e-posta gönderin. 30 saniye içinde Telegram'a özet ve yanıt taslağı gelir.
- **✅ Onayla** ile gönderin ya da diğer butonları deneyin.
- Grup e-postaları geldikçe **/gruplar** listesi dolar. İstediğiniz grubu
  "X grubunu sustur" diye yazarak veya butonlarla ayarlayabilirsiniz.
- Tüm özellikleri görmek için istediğiniz zaman **/yardim** yazın.

---

## 11. Uygulama kataloğu (isteğe bağlı)

Uygulama veya ürün geliştiriyorsanız ve insanlar size "indirme linki nedir?" diye yazıyorsa,
asistan bu e-postalara **doğru bağlantılarla otomatik yanıt** verebilir (size de rapor gelir).

1. Örnek dosyayı kopyalayın:
   ```bash
   cd /opt/mail_assistant
   sudo cp catalog.example.json catalog.json
   sudo nano catalog.json
   ```
2. Kendi uygulamalarınızı yazın. Kullanmadığınız bağlantı alanlarını boş bırakabilir veya silebilirsiniz.
   `"published": false` yaptığınız uygulama katalogda görünmez.
3. `.env` dosyasında şu satırları doldurun:
   ```
   CATALOG_JSON_PATH="/opt/mail_assistant/catalog.json"
   CATALOG_SITE_URL="https://siteniz.com"
   ```
4. Servisi yeniden başlatın:
   ```bash
   sudo systemctl restart mailagent.service
   ```
5. Telegram'da **/vitrin** yazarak kataloğun okunduğunu kontrol edin.

Uygulama adlarınız otomatik olarak **anahtar kelime alarmlarına** da eklenir; böylece gruplarda
uygulamanızdan bahsedildiğinde haberiniz olur.

Katalog tanımlı değilse otomatik yanıt özelliği tamamen kapalıdır; her e-posta onayınıza gelir.

---

## 12. Güncelleme, durdurma ve kaldırma

**Güncelleme** (ayarlarınız ve verileriniz korunur):

```bash
cd /opt/mail_assistant
sudo git pull
sudo bash install.sh
```

**Durdurma / başlatma / durum:**

```bash
sudo systemctl stop mailagent.service
sudo systemctl start mailagent.service
sudo systemctl status mailagent.service
```

> Bekçi, servisi durdurduğunuzu "çökme" sanıp 3 dakika içinde yeniden başlatır.
> Uzun süre durdurmak istiyorsanız önce bekçiyi kapatın: `crontab -e` ile `watchdog.py` satırının başına `#` koyun.

**Tamamen kaldırma:**

```bash
sudo systemctl disable --now mailagent.service
sudo rm /etc/systemd/system/mailagent.service
sudo systemctl daemon-reload
crontab -l | grep -v watchdog.py | crontab -
sudo rm -rf /opt/mail_assistant
```

---

## 13. Sorun giderme

**Kayıtları (log) görmek:**

```bash
journalctl -u mailagent.service -n 100 --no-pager      # son 100 satır
journalctl -u mailagent.service -f                      # canlı izleme (çıkmak için Ctrl + C)
```

**Bot hiç yanıt vermiyor**
- `systemctl status mailagent.service` ile servisin "active (running)" olduğunu kontrol edin.
- `.env` içindeki `TELEGRAM_ADMIN_CHAT_ID` değerinin sizin numaranız olduğundan emin olun.
  Başka biri yazarsa bot "Yetkisiz erişim" der.
- Botu Telegram'da en az bir kez **/start** ile başlatmış olmalısınız.

**/hesap_ekle "Bağlantı başarısız" diyor**
- Normal şifrenizi değil, **uygulama şifresini** girdiğinizden emin olun.
- Gmail'de 2 Adımlı Doğrulama açık değilse uygulama şifresi oluşturulamaz.
- IMAP'nin açık olduğunu kontrol edin (5. adım).

**"E-posta sunucusuna ulaşılamıyor" uyarısı geldi**
- Uygulama şifreniz iptal edilmiş veya değişmiş olabilir. **/hesap_ekle** ile aynı adresi yeni şifreyle
  tekrar ekleyin; eski kaydın üzerine yazılır.

**Taslaklarda "Gemini API hatası, standart şablon kullanıldı" notu var**
- Gemini kotanız dolmuş veya API anahtarı geçersiz olabilir. https://aistudio.google.com adresinden kontrol edin.
- Geçici bir sorunsa asistan kendiliğinden yedek modellere geçer.

**Gönderilen yanıtlar karşı tarafta spam klasörüne düşüyor**
- Kendi alan adınızı kullanıyorsanız SPF, DKIM ve DMARC kayıtlarının doğru olduğundan emin olun
  (e-posta sağlayıcınızın yönergelerine bakın).

**Bekçi müdahale mesajları sık geliyor**
- `journalctl -u mailagent.service -n 200` ile hatayı inceleyin. Bekçi, bir saatte 4'ten fazla yeniden
  başlatma olursa sizi ayrıca uyarır; bu genellikle yanlış bir ayara işaret eder.

---

## 14. Geliştirici ve İletişim

Bu bot **Ömer Göktaş** tarafından geliştirilmiştir. *"Paylaşılmayan bilgi, bilgi değildir."* vizyonuyla açık kaynak olarak paylaşılmıştır.

Kurulumla ilgili sorularınız, önerileriniz, hata bildirimleri veya geliştirmeler için doğrudan ulaşabilirsiniz:
- **E-posta (Öneriler ve İletişim):** `mail@omergoktas.net`
- **Kişisel Web Sitesi:** [omergoktas.net](https://omergoktas.net)
- **Uygulama Vitrini:** [apps.omergoktas.net](https://apps.omergoktas.net)
