import os
import re
import sys
import time
import html
import json
import hashlib
import threading
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# =====================================================================
# Configuration (Reads from config.json or Environment Variables)
# =====================================================================
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
LOCAL_CFG = {}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            LOCAL_CFG = json.load(f)
    except Exception:
        pass

PANEL_URL = os.getenv("PANEL_URL", LOCAL_CFG.get("panel_url", "http://51.75.55.16/ints/login")).rstrip("/")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", LOCAL_CFG.get("dashboard_url", "http://51.75.55.16/ints/agent/SMSCDRReports"))
USERNAME = os.getenv("PANEL_USERNAME", LOCAL_CFG.get("username", "Kkh8868himel")).strip()
PASSWORD = os.getenv("PANEL_PASSWORD", LOCAL_CFG.get("password", "KkhHimel8080Target "))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", str(LOCAL_CFG.get("poll_interval", 3))))

# Telegram Configuration
TG_TOKEN = os.getenv("TG_TOKEN", LOCAL_CFG.get("telegram_bot_token", "8999866920:AAFigVvjviEZA8KU5RjkTqnE6dEyq5w1Nw8")).strip()
TG_CHAT = os.getenv("TG_CHAT", LOCAL_CFG.get("telegram_chat_id", "6798979733")).strip()
ADMIN_ID = os.getenv("ADMIN_ID", LOCAL_CFG.get("admin_id", TG_CHAT)).strip()

# =====================================================================
# Safe Logging Utility
# =====================================================================
def log(msg: str, level: str = "INFO"):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        clean = msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
    except Exception:
        clean = msg
    print(f"[{t}] [{level}] {clean}", flush=True)

# =====================================================================
# Data Model
# =====================================================================
@dataclass
class SMSMessage:
    id: str
    service: str
    phone_number: str
    otp_code: str
    full_text: str
    timestamp: str
    carrier_range: str = ""
    has_dollar: bool = False

# =====================================================================
# Professional Telegram Bot
# =====================================================================
class TelegramBot:
    def __init__(self, token: str, chat_id: str, admin_id: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.admin_id = admin_id or chat_id
        self.last_update_id = 0
        self._listener_running = False

    def is_configured(self) -> bool:
        return bool(self.token and (self.chat_id or self.admin_id))

    def register_command_menu(self):
        """Registers ONLY the /start command in Telegram UI."""
        if not self.token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/setMyCommands"
            payload = {
                "commands": [
                    {"command": "start", "description": "🚀 Start / Check Bot Status"}
                ]
            }
            requests.post(url, json=payload, timeout=10)
        except Exception:
            pass

    def send_text(self, text: str, target_chat: str) -> bool:
        if not self.token or not target_chat:
            return False
        for attempt in range(3):
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                payload = {
                    "chat_id": target_chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return True
                elif resp.status_code == 429:
                    time.sleep(2)
            except Exception as e:
                time.sleep(1)
        return False

    def send_otp_alert(self, msg: SMSMessage) -> bool:
        target = self.chat_id or self.admin_id
        if not target:
            return False

        # Filter noise
        text_lower = (msg.full_text or "").lower()
        if any(w in text_lower for w in ["my payout", "client payout", "total sms", "payout"]):
            return False

        if not msg.phone_number or msg.phone_number == "N/A":
            return False

        safe_service = html.escape(msg.service or "SMS / OTP")
        safe_phone = html.escape(msg.phone_number or "")
        safe_range = f" | {html.escape(msg.carrier_range)}" if msg.carrier_range else ""
        dollar_badge = " 💵 <b>[$]</b>" if msg.has_dollar else ""
        safe_otp = html.escape(msg.otp_code or "N/A")
        safe_body = html.escape(msg.full_text or "")
        safe_time = html.escape(msg.timestamp or "")

        card = (
            "🔔 <b>NEW OTP RECEIVED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📱 <b>Service:</b> {safe_service}{safe_range}{dollar_badge}\n"
            f"🔑 <b>OTP Code:</b> <code>{safe_otp}</code>  <i>(Tap code to copy)</i>\n"
            f"📞 <b>Phone:</b> <code>{safe_phone}</code>\n"
            f"🕒 <b>Time:</b> {safe_time}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 <b>Message:</b>\n"
            f"<i>{safe_body}</i>\n"
        )
        success = self.send_text(card, target)
        if success:
            log(f"✅ OTP Forwarded: [{msg.service}] {msg.otp_code} -> Phone: {msg.phone_number}", "SUCCESS")
        return success

    def send_admin_ready_banner(self, web_total: int = 0):
        """Sends clean ONLINE & READY confirmation EXCLUSIVELY to Admin private chat (never in group)."""
        target = self.admin_id
        if not target:
            return
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        card = (
            "⚡ <b>TARGET SMS PRO — ONLINE & READY</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 <b>Status:</b> Active & Monitoring 24/7\n"
            f"📊 <b>Website Total SMS:</b> <code>{web_total}</code>\n"
            f"👥 <b>OTP Alert Group:</b> <code>{html.escape(str(self.chat_id))}</code>\n"
            f"⏱️ <b>Refresh Speed:</b> Every {POLL_INTERVAL}s\n"
            f"🕒 <b>Updated At:</b> <code>{now_str}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💬 <i>Listening for live incoming OTPs in real-time...</i>"
        )
        self.send_text(card, target)

    def is_admin(self, sender_id: str, chat_id: str) -> bool:
        allowed = {str(self.admin_id).strip(), str(ADMIN_ID).strip()}
        allowed.discard("")
        if not allowed:
            return True
        return str(sender_id).strip() in allowed or str(chat_id).strip() in allowed

    def start_command_listener(self):
        if self._listener_running or not self.token:
            return
        self._listener_running = True
        t = threading.Thread(target=self._command_loop, daemon=True)
        t.start()

    def _command_loop(self):
        while self._listener_running:
            try:
                url = f"https://api.telegram.org/bot{self.token}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                r = requests.get(url, params=params, timeout=25)
                if r.status_code == 200:
                    data = r.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        msg = update.get("message", {})
                        text = msg.get("text", "").strip()
                        sender_id = str(msg.get("from", {}).get("id", ""))
                        sender_chat = str(msg.get("chat", {}).get("id", ""))
                        
                        if text:
                            raw_cmd = text.split("@")[0].lower().strip()
                            if raw_cmd == "/start":
                                if not self.is_admin(sender_id, sender_chat):
                                    self.send_text("⛔ <b>Access Denied</b>\n━━━━━━━━━━━━━━━━━━━━━\nOnly the authorized Admin can control this bot.", sender_chat)
                                    continue

                                reply = (
                                    "⚡ <b>TARGET SMS PRO</b>\n"
                                    "━━━━━━━━━━━━━━━━━━━━━\n"
                                    "🟢 <b>System Status:</b> Online & Monitoring 24/7\n"
                                    "🔄 <b>Mode:</b> Real-time Live OTP Forwarder\n"
                                    f"⏱️ <b>Refresh Speed:</b> Every {POLL_INTERVAL}s\n"
                                    "━━━━━━━━━━━━━━━━━━━━━\n"
                                    "💬 <i>Live incoming OTPs are delivered automatically.</i>"
                                )
                                self.send_text(reply, sender_chat)
            except Exception:
                time.sleep(3)

# =====================================================================
# Intelligent SMS & OTP Parser
# =====================================================================
class SMSParser:
    SERVICE_KEYWORDS = [
        ("Discord", ["discord"]),
        ("Naver", ["naver"]),
        ("TWVerify", ["twverify", "shop verification"]),
        ("WhatsApp", ["whatsapp", "wa.me"]),
        ("Telegram", ["telegram", "t.me"]),
        ("Google", ["google", "g-", "gmail", "youtube"]),
        ("Facebook", ["facebook", "fb", "meta"]),
        ("Instagram", ["instagram", "ig"]),
        ("TikTok", ["tiktok"]),
        ("Microsoft", ["microsoft", "live.com", "outlook"]),
        ("Apple", ["apple", "icloud"]),
        ("Amazon", ["amazon"]),
        ("Netflix", ["netflix"]),
        ("Binance", ["binance"]),
        ("PayPal", ["paypal"]),
        ("Uber", ["uber"]),
    ]

    COUNTRIES_LIST = [
        "Palestine", "United States", "United Kingdom", "Saudi Arabia", "South Africa", "South Korea", 
        "New Zealand", "Czech Republic", "Dominican Republic", "Sri Lanka", "Costa Rica",
        "Puerto Rico", "El Salvador", "Hong Kong", "Ivory Coast", "Papua New Guinea",
        "Afghanistan", "Albania", "Algeria", "Argentina", "Armenia", "Australia", "Austria",
        "Azerbaijan", "Bahrain", "Bangladesh", "Belarus", "Belgium", "Bolivia", "Bosnia",
        "Brazil", "Bulgaria", "Cambodia", "Cameroon", "Canada", "Chile", "China", "Colombia",
        "Congo", "Croatia", "Cuba", "Cyprus", "Denmark", "Ecuador", "Egypt", "Estonia",
        "Ethiopia", "Finland", "France", "Georgia", "Germany", "Ghana", "Greece", "Guatemala",
        "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq",
        "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya",
        "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Libya", "Lithuania", "Luxembourg",
        "Madagascar", "Malaysia", "Maldives", "Mali", "Malta", "Mexico", "Moldova", "Monaco",
        "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nepal",
        "Netherlands", "Nicaragua", "Nigeria", "Norway", "Oman", "Pakistan", "Panama", "Paraguay",
        "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania", "Russia", "Rwanda",
        "Senegal", "Serbia", "Singapore", "Slovakia", "Slovenia", "Somalia", "Spain", "Sudan",
        "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand",
        "Togo", "Tunisia", "Turkey", "Turkmenistan", "Uganda", "Ukraine", "UAE", "Uruguay",
        "Uzbekistan", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"
    ]

    IGNORE_PATTERNS = [
        "my payout", "client payout", "total sms", "payout", "balance", 
        "total count", "summary", "daily report", "credit"
    ]

    @classmethod
    def extract_country_name(cls, range_text: str) -> str:
        if not range_text:
            return ""
        range_clean = range_text.strip()
        for country in cls.COUNTRIES_LIST:
            pattern = r'\b' + re.escape(country) + r'\b'
            if re.search(pattern, range_clean, re.IGNORECASE):
                return country
        parts = range_clean.split()
        return parts[0] if parts else range_clean

    @classmethod
    def extract_total_sms(cls, html_content: str) -> int:
        if not html_content:
            return 0
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            for tag in soup.find_all(string=re.compile(r'Total\s+SMS', re.IGNORECASE)):
                parent = tag.parent
                for container in [parent, parent.parent if parent else None, parent.parent.parent if parent and parent.parent else None]:
                    if container:
                        text = container.get_text(' ', strip=True)
                        m = re.search(r'Total\s+SMS\s*[:=-]?\s*(\d+)', text, re.IGNORECASE)
                        if m:
                            return int(m.group(1))
                        nums = re.findall(r'\b\d+\b', text)
                        if nums:
                            return int(nums[0])
            
            text_clean = soup.get_text(' ', strip=True)
            m = re.search(r'Total\s+SMS\s*[:=-]?\s*(\d+)', text_clean, re.IGNORECASE)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 0

    @classmethod
    def extract_otp(cls, text: str) -> str:
        if not text:
            return ""
        text = text.strip()

        # 1. Hyphenated numbers e.g. 829-102
        m = re.search(r'\b(\d{3})-(\d{3})\b', text)
        if m:
            return f"{m.group(1)}{m.group(2)}"

        # 2. "code is 910527" / "code 4108" / "code: 123456"
        m = re.search(r'(?:security code|verification code|verification|code|otp|pin|passcode|is)\s*(?:is|:|=|-)?\s*(\b\d{4,8}\b)', text, re.IGNORECASE)
        if m:
            return m.group(1)

        # 3. "760801 is your Shop verification code"
        m = re.search(r'(\b\d{4,8}\b)\s+(?:is your|is the|is|for)', text, re.IGNORECASE)
        if m:
            return m.group(1)

        # 4. Formats like G-123456 or [123456]
        m = re.search(r'\b[A-Za-z]-(\d{4,8})\b', text)
        if m:
            return m.group(0)

        # 5. Standard 6-digit code
        m = re.search(r'\b\d{6}\b', text)
        if m:
            return m.group(0)

        # 6. Any 4-8 digit code
        m = re.search(r'\b\d{4,8}\b', text)
        if m:
            return m.group(0)

        return ""

    @classmethod
    def detect_service(cls, text: str, cli_header: str = "") -> str:
        if cli_header and cli_header.strip() and not cli_header.strip().isdigit():
            return cli_header.strip()

        combined = f"{cli_header} {text}".lower()
        for svc_name, keywords in cls.SERVICE_KEYWORDS:
            for kw in keywords:
                if kw in combined:
                    return svc_name
            
        return "SMS / OTP"

    @classmethod
    def is_valid_row(cls, timestamp: str, phone: str, text: str) -> bool:
        if not text or len(text.strip()) < 5:
            return False
        
        lower_text = text.lower().strip()
        for ignored in cls.IGNORE_PATTERNS:
            if ignored in lower_text:
                return False

        clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
        if not re.search(r'^\+?\d{7,16}$', clean_phone):
            return False

        if not re.search(r'\d{4}-\d{2}-\d{2}', timestamp):
            return False

        return True

    @classmethod
    def parse_html(cls, html_content: str) -> List[SMSMessage]:
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        messages: List[SMSMessage] = []

        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue

            headers = [h.get_text(strip=True).lower() for h in rows[0].find_all(["th", "td"])]

            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue
                cols = [c.get_text(" ", strip=True) for c in cells]
                if len(cols) < 4:
                    continue

                timestamp = ""
                carrier_range = ""
                phone = ""
                cli_val = ""
                sms_text = ""
                has_dollar = False

                if "$" in " ".join(cols):
                    has_dollar = True

                if len(headers) >= len(cols):
                    for idx, val in enumerate(cols):
                        h = headers[idx]
                        if "date" in h or "time" in h:
                            timestamp = val
                        elif "range" in h:
                            carrier_range = val
                        elif "number" in h or "phone" in h:
                            phone = val
                        elif "cli" in h or "sender" in h:
                            cli_val = val
                        elif "sms" in h or "msg" in h or "text" in h:
                            sms_text = val

                if not sms_text or not phone:
                    if len(cols) >= 6:
                        timestamp = cols[0]
                        carrier_range = cols[1]
                        phone = cols[2]
                        cli_val = cols[3]
                        sms_text = cols[5]

                if not cls.is_valid_row(timestamp, phone, sms_text):
                    continue

                otp_code = cls.extract_otp(sms_text)
                service = cls.detect_service(sms_text, cli_val)
                clean_country = cls.extract_country_name(carrier_range)
                msg_id = hashlib.md5(f"{timestamp}_{phone}_{sms_text}".encode("utf-8")).hexdigest()

                messages.append(SMSMessage(
                    id=msg_id,
                    service=service,
                    phone_number=phone,
                    otp_code=otp_code,
                    full_text=sms_text,
                    timestamp=timestamp,
                    carrier_range=clean_country,
                    has_dollar=has_dollar
                ))

        return messages

# =====================================================================
# Target SMS HTTP Session & Auto Captcha Engine
# =====================================================================
class TargetSession:
    def __init__(self, base_url: str, username: str, password: str):
        if base_url.endswith("/login"):
            self.ints_base = base_url[:-6]
            self.login_url = base_url
        else:
            self.ints_base = base_url
            self.login_url = f"{self.ints_base}/login"

        self.signin_url = f"{self.ints_base}/signin"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })
        self.is_logged_in = False

    def solve_captcha(self, html_text: str) -> Optional[int]:
        m = re.search(r'What is\s*(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=\s*\?', html_text, re.IGNORECASE)
        if not m:
            m = re.search(r'(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=\s*\?', html_text)
        if m:
            n1, op, n2 = int(m.group(1)), m.group(2), int(m.group(3))
            if op == '+': return n1 + n2
            if op == '-': return n1 - n2
            if op == '*': return n1 * n2
            if op == '/': return n1 // n2 if n2 != 0 else 0
        return None

    def login(self) -> bool:
        try:
            resp = self.session.get(self.login_url, timeout=12)
            if resp.status_code != 200:
                log(f"Login page returned HTTP {resp.status_code}", "WARNING")
                return False

            captcha_ans = self.solve_captcha(resp.text)
            if captcha_ans is None:
                log("Failed to parse math captcha from login page", "WARNING")
                return False

            payload = {
                "username": self.username,
                "password": self.password,
                "capt": str(captcha_ans)
            }
            post_resp = self.session.post(self.signin_url, data=payload, allow_redirects=True, timeout=15)

            if "signin" not in post_resp.url and "login" not in post_resp.url:
                self.is_logged_in = True
                log("Authenticated successfully with panel.", "SUCCESS")
                return True

            test_resp = self.session.get(DASHBOARD_URL, allow_redirects=False, timeout=10)
            if test_resp.status_code == 200:
                self.is_logged_in = True
                log("Session active and verified.", "SUCCESS")
                return True

            log("Authentication check failed. Will retry.", "WARNING")
            self.is_logged_in = False
            return False

        except Exception as e:
            log(f"Login network issue: {e}", "WARNING")
            self.is_logged_in = False
            return False

    def fetch_dashboard(self) -> Optional[str]:
        try:
            resp = self.session.get(DASHBOARD_URL, allow_redirects=True, timeout=12)
            if "login" in resp.url or "signin" in resp.text:
                self.is_logged_in = False
                if self.login():
                    resp = self.session.get(DASHBOARD_URL, allow_redirects=True, timeout=12)
                else:
                    return None

            if resp.status_code == 200:
                return resp.text
            return None
        except Exception:
            self.is_logged_in = False
            return None

# =====================================================================
# 24/7 Continuous Monitoring Main Loop (Never Exits)
# =====================================================================
def main():
    log("==================================================", "INFO")
    log("⚡ TARGET SMS — 24/7 NON-STOP MONITORING BOT", "INFO")
    log("==================================================", "INFO")

    if not USERNAME or not PASSWORD:
        log("ERROR: Both USERNAME and PASSWORD are required!", "ERROR")
        time.sleep(10)
        return

    tg = TelegramBot(TG_TOKEN, TG_CHAT, ADMIN_ID)
    if tg.is_configured():
        tg.register_command_menu()
        tg.start_command_listener()
        log(f"Telegram alert channel: {TG_CHAT}", "INFO")

    session = TargetSession(PANEL_URL, USERNAME, PASSWORD)
    known_ids = set()
    is_first_sync = True
    consecutive_errors = 0

    log(f"Live monitoring loop started. Polling every {POLL_INTERVAL}s...", "SUCCESS")

    while True:
        try:
            if not session.is_logged_in:
                if not session.login():
                    consecutive_errors += 1
                    sleep_time = min(15, 3 * consecutive_errors)
                    time.sleep(sleep_time)
                    continue

            consecutive_errors = 0
            html = session.fetch_dashboard()

            if html:
                total_sms_on_web = SMSParser.extract_total_sms(html)
                messages = SMSParser.parse_html(html)

                if is_first_sync:
                    for msg in messages:
                        known_ids.add(msg.id)
                    log(f"Baseline established ({len(messages)} records on web). Monitoring for LIVE incoming OTPs...", "SUCCESS")
                    if tg.is_configured():
                        tg.send_admin_ready_banner(web_total=total_sms_on_web)
                    is_first_sync = False
                else:
                    for msg in messages:
                        if msg.id not in known_ids:
                            known_ids.add(msg.id)
                            dollar_str = " | 💵 $" if msg.has_dollar else ""
                            log(f"🔔 LIVE OTP! [{msg.service}] Code: {msg.otp_code} | Phone: {msg.phone_number} | Country: {msg.carrier_range}{dollar_str}", "SUCCESS")
                            if tg.is_configured():
                                tg.send_otp_alert(msg)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log("Bot shutdown requested by user.", "INFO")
            break
        except Exception as e:
            log(f"Unexpected loop exception (Auto-recovering): {e}", "WARNING")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as fatal:
            log(f"Fatal exception in outer runner (Restarting in 5s): {fatal}", "ERROR")
            time.sleep(5)
