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
    Connects to account IMAP, looks for UNSEEN emails without marking them seen (BODY.PEEK).
    Applies mailing list and blacklist filters.
    Returns list of dicts: [ {message_id, sender, subject, body, date, is_ignored, ignore_reason} ]
    """
    results = []
    imap_server = account["imap_server"]
    imap_port = int(account["imap_port"])
    email_address = account["email_address"]
    app_password = account["app_password"]

    try:
        if imap_port == 993:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=20)
        else:
            mail = imaplib.IMAP4(imap_server, imap_port, timeout=20)
            mail.starttls()
        mail.login(email_address, app_password)
        mail.select("INBOX", readonly=True)

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK" or not messages[0]:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass
            return results

        mail_ids = messages[0].split()
        for m_id in mail_ids:
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
            except Exception as e:
                logger.error(f"Error fetching mail id {m_id}: {e}")

        try:
            mail.close()
            mail.logout()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"IMAP fetch error for account {email_address}: {e}")

    return results

def mark_email_as_seen(account: dict, message_id: str):
    r"""
    Connects to account IMAP in read-write mode, locates the email by Message-ID,
    and adds the \Seen flag.
    """
    imap_server = account["imap_server"]
    imap_port = int(account["imap_port"])
    email_address = account["email_address"]
    app_password = account["app_password"]

    try:
        if imap_port == 993:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=20)
        else:
            mail = imaplib.IMAP4(imap_server, imap_port, timeout=20)
            mail.starttls()
        mail.login(email_address, app_password)
        mail.select("INBOX", readonly=False)

        status, data = mail.search(None, f'HEADER Message-ID "{message_id}"')
        if status == "OK" and data[0]:
            for num in data[0].split():
                mail.store(num, "+FLAGS", "\\Seen")
                logger.info(f"Marked mail {num} (Message-ID: {message_id}) as \\Seen")
        
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"Failed to mark email as seen for {email_address}: {e}")
        return False

def convert_text_to_clean_html(text: str) -> str:
    """
    Converts plain text reply into a clean, modern HTML version with auto-linked URLs.
    """
    escaped_text = html.escape(text)
    
    # Auto-link URLs
    url_pattern = re.compile(r'(https?://[^\s<]+)')
    linked_text = url_pattern.sub(r'<a href="\1" style="color: #1a73e8; text-decoration: underline;" target="_blank" rel="noopener">\1</a>', escaped_text)
    
    # Newlines to HTML line breaks
    formatted_body = linked_text.replace("\r\n", "\n").replace("\n", "<br>\n")
    
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
{formatted_body}
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
    if not reply_subj.lower().startswith("re:"):
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

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

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