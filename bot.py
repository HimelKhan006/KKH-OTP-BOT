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
# Configuration State (Dynamic & Admin Manageable)
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
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", str(LOCAL_CFG.get("poll_interval", 5))))

# TG_CHAT: Destination for pure OTP messages (Group / Channel / Chat ID)
TG_CHAT = os.getenv("TG_CHAT", LOCAL_CFG.get("telegram_chat_id", "")).strip()

# TG_TOKEN: Telegram Bot Token
TG_TOKEN = os.getenv("TG_TOKEN", LOCAL_CFG.get("telegram_bot_token", "")).strip()

# ADMIN_ID: Private Admin ID for system logs, status reports, and admin commands
ADMIN_ID = os.getenv("ADMIN_ID", LOCAL_CFG.get("admin_id", "")).strip()

def save_current_config():
    """Persists updated configuration to config.json if writable."""
    global LOCAL_CFG, PANEL_URL, DASHBOARD_URL, USERNAME, PASSWORD, POLL_INTERVAL, TG_TOKEN, TG_CHAT, ADMIN_ID
    LOCAL_CFG.update({
        "panel_url": PANEL_URL,
        "dashboard_url": DASHBOARD_URL,
        "username": USERNAME,
        "password": PASSWORD,
        "poll_interval": POLL_INTERVAL,
        "telegram_bot_token": TG_TOKEN,
        "telegram_chat_id": TG_CHAT,
        "admin_id": ADMIN_ID
    })
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(LOCAL_CFG, f, indent=4)
        log("Config file updated successfully.", "SUCCESS")
    except Exception as e:
        log(f"Notice: Config running in memory (Read-only environment): {e}", "WARNING")

# Global State Metrics for Command Responses
START_TIME = datetime.now()
TOTAL_CAPTURED = 0
WEBSITE_TOTAL = 0
LAST_SCAN_TIME = "Starting..."
SESSION_INSTANCE = None

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
# Interactive Admin Telegram Bot & Routing System
# =====================================================================
class TelegramBot:
    def __init__(self, token: str, otp_chat_id: str, admin_id: str = ""):
        self.token = token
        self.otp_chat_id = otp_chat_id
        self.admin_id = admin_id
        self.last_update_id = 0
        self._listener_running = False

    def is_configured(self) -> bool:
        return bool(self.token and (self.otp_chat_id or self.admin_id))

    def register_command_menu(self):
        """Registers administrative command menu in Telegram UI."""
        if not self.token:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/setMyCommands"
            payload = {
                "commands": [
                    {"command": "status", "description": "📊 Live Monitoring Status"},
                    {"command": "config", "description": "⚙️ View Active Configuration"},
                    {"command": "setuser", "description": "👤 Change Panel Username"},
                    {"command": "setpass", "description": "🔑 Change Panel Password"},
                    {"command": "setchat", "description": "👥 Change OTP Group/Chat Destination"},
                    {"command": "setadmin", "description": "👑 Set Private Admin ID"},
                    {"command": "setinterval", "description": "⏱️ Change Polling Rate (sec)"},
                    {"command": "relogin", "description": "🔄 Force Re-Authentication"},
                    {"command": "ping", "description": "⚡ Test Bot Connection"},
                    {"command": "help", "description": "❓ Admin Manual & Commands"}
                ]
            }
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                log("Registered Admin Telegram command menu successfully.", "INFO")
        except Exception as e:
            log(f"Failed to register command menu: {e}", "WARNING")

    def is_admin(self, user_id: str, chat_id: str) -> bool:
        """Verifies if the message sender is the authorized Admin."""
        allowed = {str(self.admin_id).strip(), str(ADMIN_ID).strip(), str(self.otp_chat_id).strip()}
        allowed.discard("")
        if not allowed:
            # If no admin configured, first private message sender becomes admin
            return True
        return str(user_id).strip() in allowed or str(chat_id).strip() in allowed

    def send_text(self, text: str, target_chat: str) -> bool:
        if not self.token or not target_chat:
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": target_chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            log(f"Telegram send error to {target_chat}: {e}", "ERROR")
            return False

    def send_admin_system_msg(self, text: str):
        """Sends system messages PRIVATELY to Admin only (not to group)."""
        target = self.admin_id or ADMIN_ID or self.otp_chat_id
        if target:
            self.send_text(text, target)

    def send_startup_banner(self, web_total: int = 0):
        """Sends startup/restart notification ONLY PRIVATELY to Admin."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        card = (
            "🚀 <b>TARGET SMS PRO — SYSTEM ACTIVE</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🟢 <b>Status:</b> Online & Monitoring\n"
            f"👤 <b>Account:</b> <code>{html.escape(USERNAME)}</code>\n"
            f"👥 <b>OTP Group ID:</b> <code>{html.escape(str(self.otp_chat_id))}</code>\n"
            f"📊 <b>Website Total SMS:</b> <code>{web_total}</code>\n"
            f"⏱️ <b>Refresh Rate:</b> <code>{POLL_INTERVAL}s</code>\n"
            f"🕒 <b>Started At:</b> <code>{now_str}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "💬 <i>OTPs are being sent ONLY to your configured Group.</i>\n"
            "👑 <i>System logs & admin management are delivered here privately.</i>"
        )
        self.send_admin_system_msg(card)

    def send_otp_alert(self, msg: SMSMessage) -> bool:
        """Sends LIVE OTP message ONLY to the Group / OTP destination."""
        if not self.otp_chat_id:
            # Fallback to admin if group not set
            destination = self.admin_id or ADMIN_ID
        else:
            destination = self.otp_chat_id

        if not destination:
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
        return self.send_text(card, destination)

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
                            self._handle_command(text, sender_id, sender_chat)
            except Exception:
                time.sleep(3)

    def _handle_command(self, full_text: str, user_id: str, chat_id: str):
        global USERNAME, PASSWORD, TG_CHAT, POLL_INTERVAL, SESSION_INSTANCE, ADMIN_ID

        parts = full_text.strip().split(maxsplit=1)
        raw_cmd = parts[0].lower().split("@")[0]
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Auto-bind admin if not set and user sends a private message
        if not self.admin_id and not ADMIN_ID:
            self.admin_id = user_id
            ADMIN_ID = user_id
            save_current_config()
            log(f"Auto-configured private Admin ID: {ADMIN_ID}", "SUCCESS")

        # Security Check: Reject Non-Admins
        if not self.is_admin(user_id, chat_id):
            deny_msg = (
                "⛔ <b>Access Denied</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "You are not authorized to manage this bot.\n"
                f"<i>Your ID: <code>{user_id}</code></i>"
            )
            self.send_text(deny_msg, chat_id)
            log(f"Unauthorized command attempt from user_id: {user_id} in chat: {chat_id}", "WARNING")
            return

        uptime_sec = int((datetime.now() - START_TIME).total_seconds())
        hrs, rem = divmod(uptime_sec, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hrs}h {mins}m {secs}s"

        # 1. /status
        if raw_cmd in ["/status", "/stat"]:
            reply = (
                "📊 <b>TARGET SMS — LIVE STATUS</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🟢 <b>Status:</b> Active & Monitoring\n"
                f"👤 <b>Account:</b> <code>{html.escape(USERNAME)}</code>\n"
                f"👥 <b>OTP Group:</b> <code>{html.escape(str(self.otp_chat_id))}</code>\n"
                f"📈 <b>Website Total SMS:</b> <code>{WEBSITE_TOTAL}</code>\n"
                f"📥 <b>Live Captured:</b> <code>{TOTAL_CAPTURED}</code>\n"
                f"⏱️ <b>Uptime:</b> <code>{uptime_str}</code>\n"
                f"🕒 <b>Last Check:</b> <code>{LAST_SCAN_TIME}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "⚡ <i>All systems operational.</i>"
            )
            self.send_text(reply, chat_id)

        # 2. /config or /settings
        elif raw_cmd in ["/config", "/settings"]:
            masked_pwd = (PASSWORD[:2] + "•" * max(4, len(PASSWORD) - 4) + PASSWORD[-2:]) if len(PASSWORD) > 4 else "••••"
            reply = (
                "⚙️ <b>ACTIVE BOT CONFIGURATION</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌐 <b>Login URL:</b> <code>{html.escape(PANEL_URL)}</code>\n"
                f"📊 <b>Reports URL:</b> <code>{html.escape(DASHBOARD_URL)}</code>\n"
                f"👤 <b>Username:</b> <code>{html.escape(USERNAME)}</code>\n"
                f"🔑 <b>Password:</b> <code>{html.escape(masked_pwd)}</code>\n"
                f"👥 <b>OTP Group Chat ID:</b> <code>{html.escape(str(self.otp_chat_id))}</code>\n"
                f"👑 <b>Private Admin ID:</b> <code>{html.escape(str(self.admin_id or ADMIN_ID))}</code>\n"
                f"⏱️ <b>Poll Interval:</b> <code>{POLL_INTERVAL}s</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "Commands to modify:\n"
                "• <code>/setuser &lt;username&gt;</code>\n"
                "• <code>/setpass &lt;password&gt;</code>\n"
                "• <code>/setchat &lt;group_id&gt;</code> (OTP destination)\n"
                "• <code>/setadmin &lt;admin_id&gt;</code> (Private admin)\n"
                "• <code>/setinterval &lt;seconds&gt;</code>"
            )
            self.send_text(reply, chat_id)

        # 3. /setuser <username>
        elif raw_cmd == "/setuser":
            if not arg:
                self.send_text("⚠️ <b>Usage:</b> <code>/setuser &lt;new_username&gt;</code>", chat_id)
                return
            old_user = USERNAME
            USERNAME = arg
            save_current_config()
            if SESSION_INSTANCE:
                SESSION_INSTANCE.username = USERNAME
                SESSION_INSTANCE.is_logged_in = False
            self.send_text(f"✅ <b>Username Updated!</b>\nOld: <code>{html.escape(old_user)}</code>\nNew: <code>{html.escape(USERNAME)}</code>\n\n<i>Re-authenticating...</i>", chat_id)
            log(f"Admin changed username to '{USERNAME}'", "SUCCESS")

        # 4. /setpass <password>
        elif raw_cmd == "/setpass":
            if not arg:
                self.send_text("⚠️ <b>Usage:</b> <code>/setpass &lt;new_password&gt;</code>", chat_id)
                return
            PASSWORD = arg
            save_current_config()
            if SESSION_INSTANCE:
                SESSION_INSTANCE.password = PASSWORD
                SESSION_INSTANCE.is_logged_in = False
            self.send_text("✅ <b>Password Updated!</b>\nNew password saved securely.\n\n<i>Re-authenticating with website...</i>", chat_id)
            log("Admin updated panel password via Telegram.", "SUCCESS")

        # 5. /setchat <group_id>
        elif raw_cmd == "/setchat":
            if not arg:
                self.send_text("⚠️ <b>Usage:</b> <code>/setchat &lt;group_chat_id&gt;</code> (e.g. <code>/setchat -1002345678901</code>)", chat_id)
                return
            old_chat = self.otp_chat_id
            self.otp_chat_id = arg
            TG_CHAT = arg
            save_current_config()
            self.send_text(f"✅ <b>OTP Group Destination Updated!</b>\nOld: <code>{old_chat}</code>\nNew: <code>{self.otp_chat_id}</code>\n\n<i>All live OTPs will now be sent to this group only.</i>", chat_id)
            if str(old_chat) != str(self.otp_chat_id):
                self.send_text("🔔 <b>Target SMS Bot Connected!</b>\nAll live incoming OTPs will be delivered here.", self.otp_chat_id)
            log(f"Admin changed OTP destination group ID to {self.otp_chat_id}", "SUCCESS")

        # 6. /setadmin <admin_id>
        elif raw_cmd == "/setadmin":
            if not arg:
                self.send_text("⚠️ <b>Usage:</b> <code>/setadmin &lt;your_personal_user_id&gt;</code>", chat_id)
                return
            self.admin_id = arg
            ADMIN_ID = arg
            save_current_config()
            self.send_text(f"✅ <b>Admin ID Updated!</b>\nPrivate Admin: <code>{self.admin_id}</code>\nAll system messages will be sent here privately.", chat_id)
            log(f"Admin ID set to {self.admin_id}", "SUCCESS")

        # 7. /setinterval <seconds>
        elif raw_cmd == "/setinterval":
            if not arg or not arg.isdigit():
                self.send_text("⚠️ <b>Usage:</b> <code>/setinterval &lt;seconds&gt;</code> (e.g. <code>/setinterval 3</code>)", chat_id)
                return
            POLL_INTERVAL = max(2, int(arg))
            save_current_config()
            self.send_text(f"✅ <b>Polling Interval Updated!</b>\nBot will now scan website every <code>{POLL_INTERVAL}</code> seconds.", chat_id)
            log(f"Admin updated polling interval to {POLL_INTERVAL}s", "SUCCESS")

        # 8. /relogin
        elif raw_cmd in ["/relogin", "/restart"]:
            self.send_text("🔄 <b>Re-Authenticating...</b>\nSolving math captcha and establishing fresh session...", chat_id)
            if SESSION_INSTANCE:
                SESSION_INSTANCE.is_logged_in = False
                if SESSION_INSTANCE.login():
                    self.send_text("✅ <b>Re-Authentication Successful!</b>\nBot is actively monitoring.", chat_id)
                else:
                    self.send_text("❌ <b>Re-Authentication Failed!</b>\nCheck /config username and password.", chat_id)

        # 9. /ping
        elif raw_cmd in ["/ping"]:
            reply = (
                "⚡ <b>PONG!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🟢 Bot is connected and scanning.\n"
                f"⏱️ <b>Uptime:</b> {uptime_str}\n"
                f"🕒 <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
            )
            self.send_text(reply, chat_id)

        # 10. /start
        elif raw_cmd in ["/start"]:
            reply = (
                "👑 <b>TARGET SMS PRO — ADMIN PANEL</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🟢 <b>Status:</b> Online & Monitoring\n"
                f"👤 <b>Account:</b> <code>{html.escape(USERNAME)}</code>\n"
                f"👥 <b>OTP Group:</b> <code>{html.escape(str(self.otp_chat_id))}</code>\n"
                f"📊 <b>Website SMS Total:</b> <code>{WEBSITE_TOTAL}</code>\n"
                f"📥 <b>Live Captured:</b> <code>{TOTAL_CAPTURED}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🛠️ <b>Admin Commands:</b>\n"
                "• /status — View live metrics\n"
                "• /config — View active credentials & URLs\n"
                "• <code>/setuser &lt;username&gt;</code> — Update username\n"
                "• <code>/setpass &lt;password&gt;</code> — Update password\n"
                "• <code>/setchat &lt;group_id&gt;</code> — Set OTP Group ID\n"
                "• <code>/setadmin &lt;admin_id&gt;</code> — Set Private Admin ID\n"
                "• <code>/setinterval &lt;sec&gt;</code> — Change refresh rate\n"
                "• /relogin — Force re-login\n"
                "• /help — Full command manual"
            )
            self.send_text(reply, chat_id)

        # 11. /help
        elif raw_cmd in ["/help"]:
            reply = (
                "📖 <b>TARGET SMS BOT ADMIN MANUAL</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "<b>📊 Monitoring Commands:</b>\n"
                "• <b>/status</b> — Check website total & live captured count\n"
                "• <b>/ping</b> — Test bot connection and uptime\n"
                "• <b>/relogin</b> — Force fresh login & math captcha solver\n\n"
                "<b>⚙️ Management Commands:</b>\n"
                "• <b>/config</b> — View current URLs, user, group ID & interval\n"
                "• <b>/setuser &lt;name&gt;</b> — Change website username\n"
                "• <b>/setpass &lt;pass&gt;</b> — Change website password\n"
                "• <b>/setchat &lt;id&gt;</b> — Set destination Group Chat ID for OTPs\n"
                "• <b>/setadmin &lt;id&gt;</b> — Set private Admin ID for system messages\n"
                "• <b>/setinterval &lt;sec&gt;</b> — Set scan refresh rate (2-60s)\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>OTPs go to group; system messages go privately to admin.</i>"
            )
            self.send_text(reply, chat_id)

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
        "United States", "United Kingdom", "Saudi Arabia", "South Africa", "South Korea", 
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

        # 2. "code is 910527" / "code 4108"
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
# Target SMS HTTP Session & Captcha Solver
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
            log(f"Connecting to login page: {self.login_url}...", "INFO")
            resp = self.session.get(self.login_url, timeout=12)
            if resp.status_code != 200:
                log(f"Login page returned HTTP {resp.status_code}", "ERROR")
                return False

            captcha_ans = self.solve_captcha(resp.text)
            if captcha_ans is None:
                log("Failed to parse math captcha from login page!", "ERROR")
                return False

            log(f"Math captcha solved: {captcha_ans}. Submitting credentials for '{self.username}'...", "INFO")
            payload = {
                "username": self.username,
                "password": self.password,
                "capt": str(captcha_ans)
            }
            post_resp = self.session.post(self.signin_url, data=payload, allow_redirects=True, timeout=15)

            if "signin" not in post_resp.url and "login" not in post_resp.url:
                self.is_logged_in = True
                log("Login successful! Authenticated.", "SUCCESS")
                return True

            test_resp = self.session.get(DASHBOARD_URL, allow_redirects=False, timeout=10)
            if test_resp.status_code == 200:
                self.is_logged_in = True
                log("Login verified successfully via dashboard check!", "SUCCESS")
                return True

            log("Login failed: Invalid credentials or incorrect captcha.", "ERROR")
            self.is_logged_in = False
            return False

        except Exception as e:
            log(f"Login exception: {e}", "ERROR")
            self.is_logged_in = False
            return False

    def fetch_dashboard(self) -> Optional[str]:
        try:
            resp = self.session.get(DASHBOARD_URL, allow_redirects=True, timeout=15)
            if "login" in resp.url or "signin" in resp.text:
                log("Session expired. Auto re-logging in...", "WARNING")
                self.is_logged_in = False
                if self.login():
                    resp = self.session.get(DASHBOARD_URL, allow_redirects=True, timeout=15)
                else:
                    return None

            if resp.status_code == 200:
                return resp.text
            return None
        except Exception as e:
            log(f"Error fetching dashboard: {e}", "ERROR")
            return None

# =====================================================================
# Main Execution Loop
# =====================================================================
def main():
    global TOTAL_CAPTURED, WEBSITE_TOTAL, LAST_SCAN_TIME, SESSION_INSTANCE

    log("==================================================", "INFO")
    log("⚡ TARGET SMS — GROUP OTP & ADMIN PRIVATE BOT", "INFO")
    log("==================================================", "INFO")

    if not USERNAME or not PASSWORD:
        log("ERROR: Both USERNAME and PASSWORD are required!", "ERROR")
        sys.exit(1)

    tg = TelegramBot(TG_TOKEN, TG_CHAT, ADMIN_ID)
    if tg.is_configured():
        tg.register_command_menu()
        tg.start_command_listener()
        log("Telegram alerts & Admin command listener enabled.", "INFO")
    else:
        log("Telegram alerts disabled (TG_TOKEN or TG_CHAT empty).", "WARNING")

    SESSION_INSTANCE = TargetSession(PANEL_URL, USERNAME, PASSWORD)
    if not SESSION_INSTANCE.login():
        log("Initial login attempt failed. Will retry in main loop...", "WARNING")

    known_ids = set()
    is_first_sync = True
    log(f"Bot active! Polling {DASHBOARD_URL} every {POLL_INTERVAL}s...", "SUCCESS")

    while True:
        try:
            if not SESSION_INSTANCE.is_logged_in:
                if not SESSION_INSTANCE.login():
                    time.sleep(POLL_INTERVAL)
                    continue

            html = SESSION_INSTANCE.fetch_dashboard()
            LAST_SCAN_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if html:
                total_sms_on_web = SMSParser.extract_total_sms(html)
                messages = SMSParser.parse_html(html)
                
                if total_sms_on_web == 0:
                    total_sms_on_web = len(messages)
                WEBSITE_TOTAL = total_sms_on_web

                if is_first_sync:
                    for msg in messages:
                        known_ids.add(msg.id)
                    log(f"Synced baseline (Total SMS on website: {total_sms_on_web}). Listening for LIVE incoming OTPs...", "SUCCESS")
                    if tg.is_configured():
                        tg.send_startup_banner(web_total=total_sms_on_web)
                    is_first_sync = False
                else:
                    new_count = 0
                    for msg in messages:
                        if msg.id not in known_ids:
                            known_ids.add(msg.id)
                            new_count += 1
                            TOTAL_CAPTURED += 1
                            
                            dollar_str = " | 💵 $" if msg.has_dollar else ""
                            log(f"🔔 LIVE OTP! [{msg.service}] Code: {msg.otp_code} | Phone: {msg.phone_number} | Country: {msg.carrier_range}{dollar_str}", "SUCCESS")
                            log(f"   Message: {msg.full_text}", "INFO")

                            if tg.is_configured():
                                tg.send_otp_alert(msg)

                    if new_count > 0:
                        log(f"Total on website: {total_sms_on_web} | New captured: {new_count}", "INFO")

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            log("Bot stopped by user.", "INFO")
            break
        except Exception as e:
            log(f"Loop error: {e}", "ERROR")
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
