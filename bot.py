import os
import re
import sys
import time
import html
import json
import hashlib
import threading
import requests
from datetime import datetime, timedelta
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
USERNAME = os.getenv("PANEL_USERNAME", LOCAL_CFG.get("username", "Kkh8868himel")).strip()
PASSWORD = os.getenv("PANEL_PASSWORD", LOCAL_CFG.get("password", "KkhHimel8080Target "))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", str(LOCAL_CFG.get("poll_interval", 3))))

# Telegram Configuration
TG_TOKEN = os.getenv("TG_TOKEN", LOCAL_CFG.get("telegram_bot_token", "8999866920:AAFigVvjviEZA8KU5RjkTqnE6dEyq5w1Nw8")).strip()
TG_CHAT = os.getenv("TG_CHAT", LOCAL_CFG.get("telegram_chat_id", "6798979733")).strip()
ADMIN_ID = os.getenv("ADMIN_ID", LOCAL_CFG.get("admin_id", "6798979733")).strip()

# Auto-Delete Delays (in seconds)
ONLINE_MSG_DELETE_SEC = 360  # 6 minutes
OTP_MSG_DELETE_SEC = 600     # 10 minutes

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
# Telegram Engine with Auto-Delete & Admin Lock
# =====================================================================
class TelegramBot:
    def __init__(self, token: str, chat_id: str, admin_id: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.admin_id = admin_id or chat_id
        self.last_update_id = 0
        self._listener_running = False
        self._delete_queue: List[Dict[str, Any]] = []
        self._delete_lock = threading.Lock()
        self._start_auto_deleter()

    def is_configured(self) -> bool:
        return bool(self.token and (self.chat_id or self.admin_id))

    def _start_auto_deleter(self):
        """Starts background worker that auto-deletes expired messages."""
        t = threading.Thread(target=self._auto_delete_worker, daemon=True)
        t.start()

    def schedule_deletion(self, target_chat: str, message_id: int, delay_seconds: int):
        """Schedules a message to be automatically deleted after delay_seconds."""
        if not message_id or delay_seconds <= 0:
            return
        delete_time = time.time() + delay_seconds
        with self._delete_lock:
            self._delete_queue.append({
                "chat_id": str(target_chat),
                "message_id": int(message_id),
                "delete_time": delete_time
            })

    def _auto_delete_worker(self):
        """Runs in the background and deletes expired messages."""
        while True:
            try:
                now = time.time()
                to_delete = []
                with self._delete_lock:
                    remaining = []
                    for item in self._delete_queue:
                        if now >= item["delete_time"]:
                            to_delete.append(item)
                        else:
                            remaining.append(item)
                    self._delete_queue = remaining

                for item in to_delete:
                    self.delete_message(item["chat_id"], item["message_id"])

                time.sleep(5)
            except Exception:
                time.sleep(5)

    def delete_message(self, target_chat: str, message_id: int) -> bool:
        """Calls Telegram deleteMessage API."""
        if not self.token or not target_chat or not message_id:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/deleteMessage"
            payload = {"chat_id": target_chat, "message_id": message_id}
            r = requests.post(url, json=payload, timeout=8)
            return r.status_code == 200
        except Exception:
            return False

    def register_command_menu(self):
        """Registers ONLY the /start command in Telegram UI."""
        if not self.token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/setMyCommands"
            payload = {
                "commands": [
                    {"command": "start", "description": "🚀 Check Bot Status"}
                ]
            }
            requests.post(url, json=payload, timeout=10)
        except Exception:
            pass

    def send_text(self, text: str, target_chat: str, auto_delete_sec: int = 0) -> Optional[int]:
        """Sends an HTML message and optionally schedules auto-deletion."""
        if not self.token or not target_chat:
            return None
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
                    data = resp.json()
                    msg_id = data.get("result", {}).get("message_id")
                    if auto_delete_sec > 0 and msg_id:
                        self.schedule_deletion(target_chat, msg_id, auto_delete_sec)
                    return msg_id
                elif resp.status_code == 429:
                    time.sleep(2)
            except Exception:
                time.sleep(1)
        return None

    def send_online_confirmation(self):
        """Sends clean ONLINE confirmation (auto-deletes after 6 minutes in group)."""
        msg = (
            "⚡ <b>TARGET SMS PRO — ONLINE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 <b>Status:</b> Bot is Online & Active\n"
            "🔄 <b>Mode:</b> Real-time Live OTP Forwarder\n"
            f"⏱️ <b>Speed:</b> Instant (every {POLL_INTERVAL}s)\n"
            f"⏳ <b>Auto-Delete:</b> Messages clean up automatically\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💬 <i>Ready to receive live incoming OTPs...</i>"
        )
        if self.chat_id:
            # Auto-delete from group after 6 minutes (360s)
            self.send_text(msg, self.chat_id, auto_delete_sec=ONLINE_MSG_DELETE_SEC)
        if self.admin_id and str(self.admin_id) != str(self.chat_id):
            self.send_text(msg, self.admin_id, auto_delete_sec=ONLINE_MSG_DELETE_SEC)

    def send_otp_alert(self, msg: SMSMessage) -> bool:
        """Sends live OTP alert (auto-deletes after 10 minutes)."""
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
        
        # Send OTP and auto-delete after 10 minutes (600s)
        msg_id = self.send_text(card, target, auto_delete_sec=OTP_MSG_DELETE_SEC)
        if msg_id:
            log(f"✅ OTP Forwarded (Auto-deletes in 10m): [{msg.service}] {msg.otp_code} -> Phone: {msg.phone_number}", "SUCCESS")
            return True
        return False

    def is_admin(self, sender_id: str, chat_id: str) -> bool:
        """Strict check to allow only the Admin."""
        allowed = {str(self.admin_id).strip(), str(ADMIN_ID).strip(), "6798979733"}
        allowed.discard("")
        return str(sender_id).strip() in allowed or str(chat_id).strip() in allowed

    def flush_old_updates(self):
        """Discards old messages so bot never re-answers historical commands."""
        if not self.token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            r = requests.get(url, params={"offset": -1}, timeout=10)
            if r.status_code == 200:
                results = r.json().get("result", [])
                if results:
                    self.last_update_id = results[-1]["update_id"]
        except Exception:
            pass

    def start_command_listener(self):
        if self._listener_running or not self.token:
            return
        self.flush_old_updates()
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
                                # Verify Admin authorization
                                if not self.is_admin(sender_id, sender_chat):
                                    continue

                                reply = (
                                    "⚡ <b>TARGET SMS PRO</b>\n"
                                    "━━━━━━━━━━━━━━━━━━━━━\n"
                                    "🟢 <b>System Status:</b> Online & Monitoring 24/7\n"
                                    "🔄 <b>Mode:</b> Real-time Live OTP Forwarder\n"
                                    f"⏱️ <b>Refresh Speed:</b> Every {POLL_INTERVAL}s\n"
                                    f"⏳ <b>Auto-Cleanup:</b> OTPs (10m) | Online Banner (6m)\n"
                                    "━━━━━━━━━━━━━━━━━━━━━\n"
                                    "💬 <i>Live incoming OTPs will be delivered automatically.</i>"
                                )
                                self.send_text(reply, sender_chat, auto_delete_sec=120)
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
        if not text or len(text.strip()) < 4:
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
    def parse_ajax_data(cls, aa_data: List[Any]) -> List[SMSMessage]:
        messages: List[SMSMessage] = []
        for row in aa_data:
            if not isinstance(row, list) or len(row) < 6:
                continue

            timestamp = str(row[0] or "").strip()
            carrier_range = str(row[1] or "").strip()
            phone = str(row[2] or "").strip()
            cli_val = str(row[3] or "").strip()
            sms_text = str(row[5] or "").strip()
            
            # Dollar flag
            row_joined = " ".join(str(x or "") for x in row)
            has_dollar = "$" in row_joined

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
# Target SMS HTTP Session & Live AJAX Feed
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
        self.ajax_url = f"{self.ints_base}/agent/res/data_smscdr.php"
        self.dashboard_page = f"{self.ints_base}/agent/SMSCDRReports"
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

            test_resp = self.session.get(self.dashboard_page, allow_redirects=False, timeout=10)
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

    def fetch_live_sms(self) -> List[SMSMessage]:
        """Fetches live incoming SMS records via the panel's AJAX API endpoint."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            
            params = {
                "fdate1": f"{start_date} 00:00:00",
                "fdate2": f"{today} 23:59:59",
                "frange": "",
                "fclient": "",
                "fnum": "",
                "fcli": "",
                "fgdate": "",
                "fgmonth": "",
                "fgrange": "",
                "fgclient": "",
                "fgnumber": "",
                "fgcli": "",
                "fg": "0",
                "iDisplayLength": "100"
            }
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.dashboard_page,
                "Accept": "application/json, text/javascript, */*; q=0.01"
            }

            resp = self.session.get(self.ajax_url, params=params, headers=headers, timeout=12)

            if resp.status_code == 200:
                if "Direct Script Access" in resp.text or "login" in resp.text:
                    self.is_logged_in = False
                    if self.login():
                        resp = self.session.get(self.ajax_url, params=params, headers=headers, timeout=12)
                    else:
                        return []

                try:
                    data = resp.json()
                    aa_data = data.get("aaData", [])
                    return SMSParser.parse_ajax_data(aa_data)
                except Exception:
                    return []
            else:
                self.is_logged_in = False
                return []
        except Exception:
            return []

# =====================================================================
# 24/7 Continuous Monitoring Main Loop (Never Exits)
# =====================================================================
def main():
    log("==================================================", "INFO")
    log("⚡ TARGET SMS — REAL-TIME LIVE OTP BOT", "INFO")
    log("==================================================", "INFO")

    if not USERNAME or not PASSWORD:
        log("ERROR: Both USERNAME and PASSWORD are required in config.json or environment variables!", "ERROR")
        time.sleep(10)
        return

    tg = TelegramBot(TG_TOKEN, TG_CHAT, ADMIN_ID)
    if tg.is_configured():
        tg.register_command_menu()
        tg.start_command_listener()
        log(f"Telegram alert channel: {TG_CHAT} (Admin: {ADMIN_ID})", "INFO")

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
            messages = session.fetch_live_sms()

            if is_first_sync:
                for msg in messages:
                    known_ids.add(msg.id)
                log(f"Baseline established ({len(messages)} live records synchronized from website).", "SUCCESS")
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
