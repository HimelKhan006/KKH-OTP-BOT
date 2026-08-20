# ⚡ Target SMS — Standalone Cloud Hosting Bot

Ultra-lightweight, standalone Python bot designed to run anywhere with **zero browser dependencies** and **zero GUI requirements**.

---

## 📂 Included Files in this Folder

| File | Description |
| :--- | :--- |
| **`bot.py`** | All-in-one standalone bot (Auto Captcha, Login, Country-Only Range, Dollar `$`, Total SMS, Live-Only Filter, Telegram Alerts) |
| **`requirements.txt`** | Lightweight requirements (`requests`, `beautifulsoup4`) |
| **`.env.example`** | Environment variables template |
| **`.github/workflows/run_bot.yml`** | GitHub Actions 24/7 free automated runner |
| **`Dockerfile`** | Docker image definition |
| **`docker-compose.yml`** | 1-click Docker deployment |

---

## 🚀 How to Host

### 1. Free 24/7 Hosting on GitHub Actions

1. Create a new repository on GitHub.
2. Upload all the files from this folder (`HOSTING_PACKAGE`) into your repository.
3. In your GitHub repository:
   - Go to **Settings** ➔ **Secrets and variables** ➔ **Actions**.
   - Click **New repository secret** and add:
     - `PANEL_PASSWORD`: `KkhHimel8080Target`
     - `TG_TOKEN`: `8999866920:AAEwsNbK1tmj2CQ9td5sN4fG7VhrXuqxj0Y`
     - `TG_CHAT`: `6798979733`
4. Go to **Actions** tab ➔ Click **Run Target SMS Cloud Bot** ➔ Click **Run workflow**.

---

### 2. Host on Any Linux VPS / Cloud Server / Replit / Render

```bash
pip install -r requirements.txt
python bot.py
```

---

### 3. Host with Docker

```bash
docker build -t target-sms-bot .
docker run -d --restart=always target-sms-bot
```
