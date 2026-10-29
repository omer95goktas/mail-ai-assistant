import imaplib
import smtplib
import email
from email.header import decode_header, Header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid, parseaddr, formataddr
import re
import html
import logging
from bs4 import BeautifulSoup
import config

logger = logging.getLogger(__name__)

def decode_mime_words(raw_header):
    if not raw_header:
        return ""
    decoded_fragments = []
    for fragment, charset in decode_header(raw_header):
        if isinstance(fragment, bytes):
            try:
                charset = charset or "utf-8"
                decoded_fragments.append(fragment.decode(charset, errors="replace"))
            except Exception:
                decoded_fragments.append(fragment.decode("utf-8", errors="replace"))
        else:
            decoded_fragments.append(str(fragment))
    return " ".join(decoded_fragments).strip()

def extract_body(msg) -> str:
    body_text = ""
    html_text = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            if "attachment" in content_disposition:
                continue
                
            payload = part.get_payload(decode=True)
            if not payload:
                continue
                
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded_part = payload.decode(charset, errors="replace")
            except Exception:
                decoded_part = payload.decode("utf-8", errors="replace")
                
            if content_type == "text/plain":
                body_text += decoded_part + "\n"
            elif content_type == "text/html":
                html_text += decoded_part + "\n"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
                
            if msg.get_content_type() == "text/html":
                html_text = text
            else:
                body_text = text

    if body_text.strip():
        return body_text.strip()
    elif html_text.strip():
        soup = BeautifulSoup(html_text, "html.parser")
        return soup.get_text(separator="\n", strip=True)
    return ""

def is_mailing_list_or_ignored(msg) -> tuple[bool, str]:
    """
    Checks if an email is from a mailing list, Google Groups, bulk sender or blacklisted address.
    Returns (is_ignored: bool, reason: str).
    """
    # 1. Header checks for Mailing Lists
    list_headers = [
        "List-Id",
        "List-Post",
        "List-Unsubscribe",
        "Mailing-List",
        "List-Help",
        "List-Owner"
    ]
    for lh in list_headers:
        val = msg.get(lh)
        if val:
            return True, f"Mailing List başlığı tespit edildi ({lh}: {val[:50]})"

    # Precedence check (list, bulk, junk)
    precedence = str(msg.get("Precedence", "")).lower().strip()
    if precedence in ["list", "bulk", "junk"]:
        return True, f"Precedence={precedence} tespit edildi"

    # Auto-Submitted check
    auto_submitted = str(msg.get("Auto-Submitted", "")).lower().strip()
    if auto_submitted and auto_submitted != "no":
        return True, f"Auto-Submitted={auto_submitted} tespit edildi"

    # 2. Blacklist / Address checks (From, To, Cc, Reply-To)
    from_header = str(msg.get("From", "")).lower()
    to_header = str(msg.get("To", "")).lower()
    cc_header = str(msg.get("Cc", "")).lower()
    reply_to = str(msg.get("Reply-To", "")).lower()

    combined_addrs = f"{from_header} {to_header} {cc_header} {reply_to}"

    # Check ignored domains
    for domain in getattr(config, "IGNORED_DOMAINS", ["googlegroups.com", "yahoogroups.com"]):
        if domain in combined_addrs:
            return True, f"Yoksayılan alan adı tespit edildi: {domain}"

    # Check ignored senders/keywords
    for sender_pattern in getattr(config, "IGNORED_SENDERS", ["noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster"]):
        if sender_pattern in combined_addrs:
            return True, f"Kara liste gönderici eşleşti: {sender_pattern}"

    return False, ""

def test_account_connection(email_address: str, imap_server: str, imap_port: int,
                            smtp_server: str, smtp_port: int, app_password: str):
    # Test IMAP
    try:
        if imap_port == 993:
            imap_conn = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=15)
        else:
            imap_conn = imaplib.IMAP4(imap_server, imap_port, timeout=15)
            imap_conn.starttls()
        imap_conn.login(email_address, app_password)
        imap_conn.logout()
    except Exception as e:
        return False, f"IMAP Bağlantı Hatası: {e}"

    # Test SMTP
    try:
        if smtp_port == 465:
            smtp_conn = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
            smtp_conn.ehlo()
        else:
            smtp_conn = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
            smtp_conn.ehlo()
            smtp_conn.starttls()
            smtp_conn.ehlo()
        smtp_conn.login(email_address, app_password)
        smtp_conn.quit()
    except Exception as e:
        return False, f"SMTP Bağlantı Hatası: {e}"

    return True, "Bağlantı başarılı."

def fetch_unseen_emails(account: dict):
    r"""
    Connects to account IMAP in read-write mode, fetches UNSEEN emails,
    marks them as \Seen immediately in the SAME session to prevent queue choking,
    applies mailing list and blacklist filters, and returns email objects.
    """
    results = []
    imap_server = account["imap_server"]
    imap_port = int(account["imap_port"])
    email_address = account["email_address"]
    app_password = account["app_password"]

    mail = None
    try:
        if imap_port == 993:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=12)
        else:
            mail = imaplib.IMAP4(imap_server, imap_port, timeout=12)
            mail.starttls()
        mail.login(email_address, app_password)
        mail.select("INBOX", readonly=False)

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            return results

        mail_ids = messages[0].split()
        # Newest emails are at the end; inspect newest first (limit to last 15)
        recent_ids = list(reversed(mail_ids))[:15]
        for m_id in recent_ids:
            try:
                res, data = mail.fetch(m_id, "(BODY.PEEK[])")
                if res != "OK":
                    continue

                for response_part in data:
                    if isinstance(response_part, tuple):
                        raw_email = response_part[1]
                        msg = email.message_from_bytes(raw_email)

                        msg_id = decode_mime_words(msg.get("Message-ID", "")).strip()
                        if not msg_id:
                            msg_id = f"uid-{m_id.decode()}-{account['id']}"

                        sender = decode_mime_words(msg.get("From", "")).strip()
                        subject = decode_mime_words(msg.get("Subject", "(Konusuz)")).strip()
                        date_str = decode_mime_words(msg.get("Date", "")).strip()
                        
                        # Filter check
                        is_ignored, ignore_reason = is_mailing_list_or_ignored(msg)

                        body = ""
                        if not is_ignored:
                            body = extract_body(msg)

                        results.append({
                            "message_id": msg_id,
                            "sender": sender,
                            "subject": subject,
                            "body": body,
                            "date": date_str,
                            "raw_num": m_id.decode(),
                            "is_ignored": is_ignored,
                            "ignore_reason": ignore_reason
                        })
                
                # Mark as \Seen immediately inside the same IMAP connection!
                try:
                    mail.store(m_id, "+FLAGS", "\\Seen")
                except Exception as ex_seen:
                    logger.warning(f"Could not mark mail {m_id} as \\Seen: {ex_seen}")

            except Exception as e:
                logger.error(f"Error fetching mail id {m_id}: {e}")

    except Exception as e:
        logger.error(f"IMAP fetch error for account {email_address}: {e}")
    finally:
        if mail:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass

    return results

def mark_email_as_seen(account: dict, message_id: str):
    r"""
    Helper to mark an email as seen. Since fetch_unseen_emails marks emails
    as \Seen directly during the fetch cycle, this is a fast no-op fallback.
    """
    return True

def format_signature_html(text: str) -> tuple[str, str]:
    """
    Extracts the signature from the end of the text and returns (body_text, signature_html).
    Produces the requested transparent signature format:
    <p>
    Saygılarımla,<br>
    Gemini (Ömer Göktaş Asistanı)<br>
    Onaylayan: Ömer Göktaş<br>
    <a href="https://apps.omergoktas.net">apps.omergoktas.net</a>
    </p>
    """
    lines = text.strip().splitlines()
    idx_omer = -1
    for i in range(len(lines) - 1, max(-1, len(lines) - 8), -1):
        line_clean = lines[i].strip().lower()
        if "ömer göktaş" in line_clean or "omer goktas" in line_clean or "gemini" in line_clean or "onaylayan" in line_clean:
            idx_omer = i
            break

    if idx_omer != -1:
        has_closing = False
        closing_text = ""
        # Search backwards from signature for closing phrase (e.g. Saygılarımla)
        for j in range(idx_omer - 1, max(-1, idx_omer - 4), -1):
            prec = lines[j].strip()
            if any(prec.lower().startswith(w) for w in ["saygı", "iyi ", "teşekkür", "kolay", "sevgi"]):
                has_closing = True
                closing_text = prec
                body_lines = lines[:j]
                break
        if not has_closing:
            body_lines = lines[:idx_omer]

        closing_html = f"{html.escape(closing_text)}<br>" if has_closing else "Saygılarımla,<br>"
        sig_html = (
            f'<p style="margin-top: 20px; margin-bottom: 0; line-height: 1.6;">'
            f'{closing_html}'
            f'Gemini (Ömer Göktaş Asistanı)<br>'
            f'Onaylayan: Ömer Göktaş<br>'
            f'<a href="https://apps.omergoktas.net" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">apps.omergoktas.net</a>'
            f'</p>'
        )
        return "\n".join(body_lines).strip(), sig_html
    else:
        sig_html = (
            f'<p style="margin-top: 20px; margin-bottom: 0; line-height: 1.6;">'
            f'Saygılarımla,<br>'
            f'Gemini (Ömer Göktaş Asistanı)<br>'
            f'Onaylayan: Ömer Göktaş<br>'
            f'<a href="https://apps.omergoktas.net" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">apps.omergoktas.net</a>'
            f'</p>'
        )
        return text.strip(), sig_html

def convert_text_to_clean_html(text: str) -> str:
    """
    Converts plain text reply into clean, spam-optimized HTML where no raw URLs appear naked.
    URLs are converted into semantic anchor text (e.g. Uygulama Vitrini, Google Play Mağazası),
    and signature matches:
    <p>Ömer Göktaş<br><a href="https://apps.omergoktas.net">apps.omergoktas.net</a></p>
    """
    body_text, sig_html = format_signature_html(text)
    body_escaped = html.escape(body_text)

    # 1. Replace known label + URL patterns (e.g. "Google Play: https://...")
    labeled_replacements = [
        (re.compile(r'(Google\s*Play(?:\s*Mağazası)?)\s*:\s*(https?://[^\s<]+)', re.IGNORECASE),
         r'<a href="\2" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">Google Play Mağazası</a>'),
        (re.compile(r'(Microsoft\s*Store)\s*:\s*(https?://[^\s<]+)', re.IGNORECASE),
         r'<a href="\2" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">Microsoft Store</a>'),
        (re.compile(r'(GitHub(?:\s*Deposu)?)\s*:\s*(https?://[^\s<]+)', re.IGNORECASE),
         r'<a href="\2" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">GitHub Deposu</a>'),
        (re.compile(r'(Doğrudan\s*İndirme(?:\s*Bağlantısı)?)\s*:\s*(https?://[^\s<]+)', re.IGNORECASE),
         r'<a href="\2" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">Doğrudan İndirme Bağlantısı</a>'),
        (re.compile(r'(Vitrin(?:\s*Detay\s*Sayfası|\s*Sitesi)?)\s*:\s*(https?://[^\s<]+)', re.IGNORECASE),
         r'<a href="\2" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">Uygulama Vitrini</a>'),
    ]

    for pat, repl in labeled_replacements:
        body_escaped = pat.sub(repl, body_escaped)

    # 2. Replace any remaining naked URLs not already in href
    def replace_naked_url(match):
        raw_url = match.group(0)
        url_lower = raw_url.lower()
        if "apps.omergoktas.net/app/" in url_lower:
            anchor = "Uygulama Detay Sayfası"
        elif "apps.omergoktas.net" in url_lower:
            anchor = "Uygulama Vitrini"
        elif "play.google.com" in url_lower:
            anchor = "Google Play Mağazası"
        elif "apps.microsoft.com" in url_lower or "microsoft.com/store" in url_lower:
            anchor = "Microsoft Store"
        elif "github.com" in url_lower:
            anchor = "GitHub Deposu"
        elif url_lower.endswith((".apk", ".exe", ".zip", ".msi", ".dmg")):
            anchor = "İndirme Bağlantısı"
        else:
            anchor = "İlgili Bağlantı"
        return f'<a href="{raw_url}" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">{anchor}</a>'

    url_pattern = re.compile(r'(?<!href=")(https?://[^\s<"]+)')
    body_escaped = url_pattern.sub(replace_naked_url, body_escaped)

    # 3. Format paragraphs
    paragraphs = [p.strip() for p in body_escaped.split("\n\n") if p.strip()]
    formatted_paragraphs = []
    for p in paragraphs:
        lines = p.replace("\r\n", "\n").split("\n")
        formatted_paragraphs.append(f'<p style="margin-top: 0; margin-bottom: 12px; line-height: 1.6;">{"<br>".join(lines)}</p>')

    body_html = "\n".join(formatted_paragraphs)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.6;
    color: #202124;
    background-color: #ffffff;
    margin: 0;
    padding: 12px;
}}
a {{
    color: #1a73e8;
    text-decoration: underline;
}}
</style>
</head>
<body>
<div>
{body_html}
{sig_html}
</div>
</body>
</html>"""

def send_reply_email(account: dict, to_email: str, subject: str, in_reply_to: str, draft_reply: str):
    """
    Sends email reply via SMTP with In-Reply-To, References, standard From header,
    Message-ID domain override, and MIMEMultipart alternative (text/plain + text/html).
    """
    smtp_server = account["smtp_server"]
    smtp_port = int(account["smtp_port"])
    email_address = account["email_address"]
    app_password = account["app_password"]

    _, clean_to = parseaddr(to_email)
    if not clean_to:
        clean_to = to_email.strip()

    reply_subj = subject.strip()
    if in_reply_to and not reply_subj.lower().startswith("re:"):
        reply_subj = f"Re: {reply_subj}"

    # 1. Clean sender address and format standard From header
    _, sender_email = parseaddr(email_address)
    if not sender_email:
        sender_email = email_address.strip()

    # 2. Override Message-ID domain to prevent @debian local hostname
    domain = sender_email.split("@")[-1] if "@" in sender_email else "omergoktas.net"
    if not domain or domain.lower() in ["localhost", "debian"]:
        domain = "omergoktas.net"

    # 3. Create MIMEMultipart('alternative') with text/plain + text/html
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((str(Header("Ömer Göktaş", "utf-8")), sender_email))
    msg["To"] = clean_to
    msg["Subject"] = reply_subj
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain)

    # 4. Strict thread header enforcement (In-Reply-To & References)
    if in_reply_to:
        ref_id = str(in_reply_to).strip()
        if ref_id:
            if not ref_id.startswith("<"):
                ref_id = f"<{ref_id}"
            if not ref_id.endswith(">"):
                ref_id = f"{ref_id}>"
            msg["In-Reply-To"] = ref_id
            msg["References"] = ref_id
            logger.info(f"Thread headers set: In-Reply-To={ref_id}, References={ref_id}")

    # Attach text/plain
    part_plain = MIMEText(draft_reply, "plain", "utf-8")
    msg.attach(part_plain)

    # Attach text/html
    html_content = convert_text_to_clean_html(draft_reply)
    part_html = MIMEText(html_content, "html", "utf-8")
    msg.attach(part_html)

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=25)
            server.ehlo()
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=25)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(email_address, app_password)
        server.send_message(msg)
        server.quit()
        logger.info(f"Successfully sent reply to {clean_to} from {email_address} (Message-ID: {msg['Message-ID']})")
        return True, "E-posta başarıyla gönderildi."
    except Exception as e:
        logger.error(f"Failed to send email via SMTP {smtp_server}:{smtp_port}: {e}")
        return False, str(e)