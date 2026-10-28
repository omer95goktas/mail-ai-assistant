import json
import logging
from google import genai
from google.genai import types
import config
import app_catalog

logger = logging.getLogger(__name__)

FALLBACK_REPLY_TEMPLATE = """Merhaba,

E-postanız için teşekkür ederim. İletinizi aldım ve en kısa sürede detaylı olarak dönüş yapacağım. Paylaşılmayan bilgi, bilgi değildir anlayışıyla her türlü soru ve iş birliğine açığım.

Tüm açık kaynak ve erişilebilirlik uygulamalarıma https://apps.omergoktas.net vitrin adresinden de ulaşabilirsiniz.

Saygılarımla,
Ömer Göktaş"""

class AIService:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        self.model = config.GEMINI_MODEL or "gemini-3.5-flash"
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=15000))
            except Exception as e:
                logger.error(f"Gemini client initialization error: {e}")

    def analyze_email(self, sender: str, subject: str, body: str) -> dict:
        """
        Analyzes the email with real-time app catalog data and returns:
        {
            "is_link_request": bool,
            "requested_app": str or None,
            "summary": str,
            "reply_body": str,
            "auto_send": bool,
            "ai_generated": bool,
            "error_note": str or None
        }
        """
        if not self.client:
            return {
                "is_link_request": False,
                "requested_app": None,
                "summary": f"Konu: {subject}\nGönderen: {sender}",
                "reply_body": FALLBACK_REPLY_TEMPLATE,
                "auto_send": False,
                "ai_generated": False,
                "error_note": "Gemini API istemcisi başlatılamadı."
            }

        catalog_context = app_catalog.get_catalog_prompt_context()

        prompt = f"""Sen Ömer Göktaş adına e-postaları inceleyip yanıtlayan profesyonel bir yapay zeka asistanısın.
Ömer Göktaş'ın temel vizyon ve felsefesi: "Paylaşılmayan bilgi, bilgi değildir".
Üslup: Son derece kibar, net, profesyonel, samimi, yapıcı ve çözüm odaklı.

=== VİTRİN SİTESİ VE GÜNCEL UYGULAMA KATALOĞU ===
{catalog_context}
================================================

AŞAĞIDAKİ GELEN E-POSTAYI İNCELE:
GÖNDEREN: {sender}
KONU: {subject}
İÇERİK:
{body[:4000]}

GÖREVLER VE NIYET ANALİZİ (INTENT DETECTION):
1. "is_link_request": Gelen e-posta yukarıdaki katalogda yer alan herhangi bir uygulamanın indirme linkini, mağaza linkini (Google Play, Microsoft Store, GitHub, doğrudan indirme linki), son sürümünü ya da vitrin sitesini (apps.omergoktas.net) mi soruyor/talep ediyor? (true veya false)
2. "requested_app": İstenen uygulamanın tam adı (Örn: "Engelsiz Android", "Erişilebilir Kitap Okuyucu", "Medya Belge İşleme Merkezi" vb.). Belirli bir uygulama sorulmuyorsa ya da link talebi değilse null yap.
3. "auto_send": 
   - EĞER e-posta net bir şekilde uygulama indirme linki, mağaza linki, son sürüm veya vitrin adresi soruyorsa -> true olmalı.
   - FAKAT e-posta iş birliği, teknik hata/arıza bildirimi, kişisel soru, geliştirme önerisi veya insan onayı gerektiren karmaşık bir konu içeriyorsa -> false olmalı.
4. "summary": E-postanın 1-2 cümlelik net, Türkçe özeti.
5. "reply_body": Ömer Göktaş adına gönderilecek eksiksiz, samimi, kibar ve profesyonel yanıt taslağı:
   - "Paylaşılmayan bilgi, bilgi değildir" felsefesine uygun olsun.
   - İstenen uygulama(lar) için yukarıdaki katalogdaki doğru resmi bağlantıları (Google Play, Microsoft Store, GitHub, Doğrudan İndirme veya https://apps.omergoktas.net vitrin bağlantısını) mutlaka açık ve net olarak ekle.
   - Nazik bir selamlama ile başla ve sonda şu imzayı kullan:
     Saygılarımla,
     Ömer Göktaş

ÇIKTI FORMATI:
Sadece aşağıdaki JSON formatında, geçerli bir JSON nesnesi döndür:
{{
  "is_link_request": true,
  "requested_app": "Uygulama Adı veya null",
  "summary": "...",
  "reply_body": "...",
  "auto_send": true
}}
"""
        models_to_try = [self.model, "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
        seen_models = set()
        unique_models = []
        for m in models_to_try:
            if m and m not in seen_models:
                seen_models.add(m)
                unique_models.append(m)

        last_error = None
        for m in unique_models:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.4,
                        response_mime_type="application/json"
                    )
                )
                text = response.text.strip()
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines and lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()
                data = json.loads(text)
                
                is_link_req = bool(data.get("is_link_request", False))
                req_app = data.get("requested_app")
                if req_app and str(req_app).lower() == "null":
                    req_app = None

                summary = (data.get("summary") or "").strip()
                reply_body = (data.get("reply_body") or "").strip()
                auto_send = bool(data.get("auto_send", False))

                if summary and reply_body:
                    return {
                        "is_link_request": is_link_req,
                        "requested_app": req_app,
                        "summary": summary,
                        "reply_body": reply_body,
                        "auto_send": auto_send,
                        "ai_generated": True,
                        "error_note": None
                    }
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini generation with {m} failed: {e}")

        err_msg = str(last_error) if last_error else "Bilinmeyen hata"
        return {
            "is_link_request": False,
            "requested_app": None,
            "summary": f"{subject} konulu gelen e-posta ({sender}).",
            "reply_body": FALLBACK_REPLY_TEMPLATE,
            "auto_send": False,
            "ai_generated": False,
            "error_note": f"⚠️ Not: Gemini API hatası ({err_msg[:60]}). Standart şablon kullanıldı."
        }

    def regenerate_reply(self, sender: str, subject: str, body: str, current_draft: str) -> str:
        """
        Regenerates an alternative reply with a different tone and perspective.
        """
        if not self.client:
            return current_draft

        catalog_context = app_catalog.get_catalog_prompt_context()

        prompt = f"""Sen Ömer Göktaş adına e-postaları yanıtlayan profesyonel bir yapay zeka asistanısın.
Ömer Göktaş'ın temel vizyon ve felsefesi: "Paylaşılmayan bilgi, bilgi değildir".
Üslup: Nazik, net, profesyonel, samimi ve çözüm odaklı.

=== VİTRİN VE UYGULAMA KATALOĞU ===
{catalog_context}
===================================

GELEN E-POSTA BİLGİLERİ:
Gönderen: {sender}
Konu: {subject}
İçerik: {body[:3000]}

DAHA ÖNCE HAZIRLANAN TASLAK:
{current_draft}

GÖREV:
Bu e-posta için yukarıda daha önce hazırlanan taslaktan FARKLI, alternatif bir ton ve yaklaşımla (örneğin daha detaylı, farklı vurgularla veya daha samimi/özet bir dille) YENİ ve eksiksiz bir Türkçe e-posta yanıt taslağı hazırla.
- "Paylaşılmayan bilgi, bilgi değildir" felsefesine sadık kal.
- Eğer konu bir uygulama ise ilgili doğru indirme/mağaza linkini mutlaka koru.
- Uygun bir selamlama ile başla ve sonda 'Saygılarımla,\nÖmer Göktaş' imzasını kullan.

Sadece yeni e-posta yanıt taslağı metnini döndür (başka açıklama veya JSON ekleme)."""

        models_to_try = [self.model, "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
        seen_models = set()
        unique_models = [m for m in models_to_try if m and not (m in seen_models or seen_models.add(m))]
        for m in unique_models:
            try:
                res = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.8)
                )
                text = res.text.strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"Regenerate with {m} failed: {e}")

        return current_draft

    def refine_reply_with_instruction(self, sender: str, subject: str, body: str, current_draft: str, instruction: str) -> str:
        """
        Reshapes the draft reply according to specific user instructions.
        """
        if not self.client:
            return current_draft

        catalog_context = app_catalog.get_catalog_prompt_context()

        prompt = f"""Sen Ömer Göktaş adına e-postaları yanıtlayan profesyonel bir yapay zeka asistanısın.
Ömer Göktaş'ın temel felsefesi: "Paylaşılmayan bilgi, bilgi değildir".
Üslup: Kibar, net, profesyonel ve samimi.

=== VİTRİN VE UYGULAMA KATALOĞU ===
{catalog_context}
===================================

GELEN E-POSTA:
Gönderen: {sender}
Konu: {subject}
İçerik: {body[:3000]}

MEVCUT YANIT TASLAĞI:
{current_draft}

KULLANICININ (ÖMER GÖKTAŞ) ÖZEL DÜZENLEME TALİMATI:
"{instruction}"

GÖREV:
Yukarıdaki mevcut yanıt taslağını kullanıcının verdiği özel talimata göre YENİDEN ŞEKİLLENDİR.
- Talimatta istenen değişiklikleri, yeni bilgileri veya tonu tam olarak uygula.
- "Paylaşılmayan bilgi, bilgi değildir" vizyonunu koru.
- Nazik bir selamlama ile başla ve sonda 'Saygılarımla,\nÖmer Göktaş' imzasını kullan.

Sadece revize edilmiş yeni e-posta yanıt metnini döndür (başka açıklama veya JSON ekleme)."""

        models_to_try = [self.model, "gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
        seen_models = set()
        unique_models = [m for m in models_to_try if m and not (m in seen_models or seen_models.add(m))]
        for m in unique_models:
            try:
                res = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.5)
                )
                text = res.text.strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"Refine with {m} failed: {e}")

        return current_draft