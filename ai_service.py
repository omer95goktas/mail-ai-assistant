import json
import logging
from google import genai
from google.genai import types
import config
import app_catalog

logger = logging.getLogger(__name__)

FALLBACK_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]


def signature_block() -> str:
    lines = ["Saygılarımla,", config.ASSISTANT_SIGNATURE_NAME, f"Onaylayan: {config.OWNER_FULL_NAME}"]
    if config.SIGNATURE_URL:
        lines.append(config.SIGNATURE_URL)
    return "\n".join(lines)


def fallback_reply() -> str:
    return (
        "Merhaba,\n\n"
        f"Ben {config.OWNER_ADDRESS_POSSESSIVE} yapay zekâ asistanıyım. E-postanızı aldım; "
        f"{config.OWNER_ADDRESS} en kısa sürede size dönüş yapacaktır.\n\n"
        f"{config.TRANSPARENCY_NOTE}\n\n"
        f"{signature_block()}"
    )


# Geriye dönük uyumluluk (bot.py içinde kullanılıyor)
FALLBACK_REPLY_TEMPLATE = fallback_reply()


def persona_rules() -> str:
    return f"""KİMLİK, ŞEFFAFLIK VE ÜSLUP KURALLARI:
1. KİMLİK: Kendini mutlaka "{config.OWNER_ADDRESS_POSSESSIVE} yapay zekâ asistanı" olarak tanıt. (Örn: "Merhaba, ben {config.OWNER_ADDRESS_POSSESSIVE} yapay zekâ asistanıyım...")
2. ŞEFFAFLIK: Metin içinde açıkça ve eksiksiz olarak şu ifadeye yer ver:
   "{config.TRANSPARENCY_NOTE}"
3. Kalıplaşmış slogan kullanma. Samimi, nazik, net ve yardımsever ol; doğrudan kişinin ihtiyacına odaklan.
4. Birinci tekil şahıs kullan; "biz/ekibimiz" gibi kurumsal ifadeler kullanma.
5. İMZA: Yanıtın sonunda MUTLAKA şu imzayı aynen kullan:
{signature_block()}"""


class AIService:
    def __init__(self):
        self.api_key = config.GEMINI_API_KEY
        self.model = config.GEMINI_MODEL or FALLBACK_MODELS[0]
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=15000))
            except Exception as e:
                logger.error(f"Gemini client initialization error: {e}")

    def _models(self):
        seen, out = set(), []
        for m in [self.model] + FALLBACK_MODELS:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def analyze_email(self, sender: str, subject: str, body: str) -> dict:
        """
        Döndürür: {is_link_request, requested_app, summary, reply_body, auto_send, ai_generated, error_note}
        """
        if not self.client:
            return {
                "is_link_request": False, "requested_app": None,
                "summary": f"Konu: {subject}\nGönderen: {sender}",
                "reply_body": fallback_reply(), "auto_send": False, "ai_generated": False,
                "error_note": "Gemini API istemcisi başlatılamadı (GEMINI_API_KEY kontrol edin).",
            }

        has_catalog = app_catalog.has_catalog()
        catalog_context = app_catalog.get_catalog_prompt_context() if has_catalog else "(Katalog tanımlı değil.)"

        catalog_rules = (
            "6. KATALOG: İstenen uygulama(lar) için aşağıdaki katalogdaki doğru resmi bağlantıları açıkça ekle."
            if has_catalog else
            "6. Katalog tanımlı değil; bağlantı veya uygulama bilgisi uydurma."
        )

        prompt = f"""Sen {config.OWNER_FULL_NAME} adlı kişinin yapay zekâ e-posta asistanısın (Gemini). Gelen e-postayı inceleyip {config.OWNER_ADDRESS_POSSESSIVE} yapay zekâ asistanı olarak açık, şeffaf, samimi ve net bir Türkçe yanıt hazırla.

{persona_rules()}
{catalog_rules}

=== UYGULAMA KATALOĞU ===
{catalog_context}
=========================

GELEN E-POSTA:
GÖNDEREN: {sender}
KONU: {subject}
İÇERİK:
{body[:4000]}

GÖREVLER:
1. "is_link_request": E-posta katalogdaki bir uygulamanın indirme/mağaza linkini, son sürümünü veya katalog sitesini mi istiyor? (true/false){"" if has_catalog else " Katalog olmadığı için her zaman false."}
2. "requested_app": İstenen uygulamanın tam adı; yoksa null.
3. "auto_send": Yalnızca e-posta NET bir şekilde katalogdaki bir uygulamanın linkini istiyorsa true. İş birliği, hata bildirimi, kişisel soru, öneri veya insan onayı gerektiren her konuda false.{"" if has_catalog else " Katalog olmadığı için her zaman false."}
4. "summary": E-postanın 1-2 cümlelik Türkçe özeti.
5. "reply_body": Yukarıdaki kurallara uygun, imzalı, eksiksiz Türkçe yanıt taslağı.

Sadece şu JSON'u döndür:
{{"is_link_request": false, "requested_app": null, "summary": "...", "reply_body": "...", "auto_send": false}}
"""
        last_error = None
        for m in self._models():
            try:
                response = self.client.models.generate_content(
                    model=m, contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.4, response_mime_type="application/json"),
                )
                text = (response.text or "").strip()
                if text.startswith("```"):
                    text = "\n".join(l for l in text.splitlines() if not l.startswith("```")).strip()
                data = json.loads(text)

                req_app = data.get("requested_app")
                if req_app and str(req_app).lower() == "null":
                    req_app = None
                summary = (data.get("summary") or "").strip()
                reply_body = (data.get("reply_body") or "").strip()
                auto_send = bool(data.get("auto_send", False)) and has_catalog

                if summary and reply_body:
                    return {
                        "is_link_request": bool(data.get("is_link_request", False)) and has_catalog,
                        "requested_app": req_app, "summary": summary, "reply_body": reply_body,
                        "auto_send": auto_send, "ai_generated": True, "error_note": None,
                    }
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini generation with {m} failed: {e}")

        err_msg = str(last_error) if last_error else "Bilinmeyen hata"
        return {
            "is_link_request": False, "requested_app": None,
            "summary": f"{subject} konulu gelen e-posta ({sender}).",
            "reply_body": fallback_reply(), "auto_send": False, "ai_generated": False,
            "error_note": f"⚠️ Not: Gemini API hatası ({err_msg[:60]}). Standart şablon kullanıldı.",
        }

    def _generate_text(self, prompt: str, temperature: float, fallback: str, label: str) -> str:
        if not self.client:
            return fallback
        for m in self._models():
            try:
                res = self.client.models.generate_content(
                    model=m, contents=prompt, config=types.GenerateContentConfig(temperature=temperature))
                text = (res.text or "").strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"{label} with {m} failed: {e}")
        return fallback

    def regenerate_reply(self, sender: str, subject: str, body: str, current_draft: str) -> str:
        """Farklı bir ton ve yaklaşımla yeni bir yanıt taslağı üretir."""
        prompt = f"""Sen {config.OWNER_FULL_NAME} adlı kişinin yapay zekâ e-posta asistanısın (Gemini).

{persona_rules()}

=== UYGULAMA KATALOĞU ===
{app_catalog.get_catalog_prompt_context() if app_catalog.has_catalog() else "(Katalog tanımlı değil; bağlantı uydurma.)"}
=========================

GELEN E-POSTA:
Gönderen: {sender}
Konu: {subject}
İçerik: {body[:3000]}

DAHA ÖNCE HAZIRLANAN TASLAK:
{current_draft}

GÖREV: Bu e-posta için önceki taslaktan FARKLI bir ton ve yaklaşımla (örneğin daha kısa ve öz) YENİ ve eksiksiz bir Türkçe yanıt hazırla. Uygulama bağlantıları varsa koru. Uygun bir selamlamayla başla ve yukarıdaki imzayı aynen kullan.

Sadece yeni yanıt metnini döndür (açıklama veya JSON ekleme)."""
        return self._generate_text(prompt, 0.8, current_draft, "Regenerate")

    def refine_reply_with_instruction(self, sender: str, subject: str, body: str,
                                      current_draft: str, instruction: str) -> str:
        """Taslağı kullanıcının özel talimatına göre yeniden şekillendirir."""
        prompt = f"""Sen {config.OWNER_FULL_NAME} adlı kişinin yapay zekâ e-posta asistanısın (Gemini).

{persona_rules()}

=== UYGULAMA KATALOĞU ===
{app_catalog.get_catalog_prompt_context() if app_catalog.has_catalog() else "(Katalog tanımlı değil; bağlantı uydurma.)"}
=========================

GELEN E-POSTA:
Gönderen: {sender}
Konu: {subject}
İçerik: {body[:3000]}

MEVCUT YANIT TASLAĞI:
{current_draft}

KULLANICININ ({config.OWNER_FULL_NAME}) ÖZEL DÜZENLEME TALİMATI:
"{instruction}"

GÖREV: Mevcut taslağı bu talimata göre YENİDEN ŞEKİLLENDİR. İstenen değişiklikleri, bilgileri ve tonu tam olarak uygula. Uygun bir selamlamayla başla ve yukarıdaki imzayı aynen kullan.

Sadece revize edilmiş yanıt metnini döndür (açıklama veya JSON ekleme)."""
        return self._generate_text(prompt, 0.5, current_draft, "Refine")
