# 📢 Telegram Marketing Bot

A powerful multi-account Telegram message forwarding bot.
Control multiple Telegram user accounts from one bot — add messages, pick accounts, and blast to every group you're a member of.

---

## 🗂 Project Structure

```
marketing_bot/
├── bot.py            ← Main bot (PTB handlers + menus)
├── userbot.py        ← Telethon engine (sessions + forwarding)
├── storage.py        ← JSON persistence layer
├── config.py         ← Configuration loader
├── requirements.txt
├── .env              ← Your secrets (create from .env.example)
├── data/
│   └── db.json       ← Auto-created: accounts, messages, settings
└── sessions/
    └── *.session     ← Auto-created: one per Telegram account
```

---

## ⚡ Quick Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

> **Pydroid3 on Android:** Open Pydroid3 → Terminal tab → run the pip command above.

---

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and set your Bot Token:

```
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
ADMIN_IDS=123456789
```

- Get a bot token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID: message [@userinfobot](https://t.me/userinfobot)

---

### 3. Run the bot

```bash
python bot.py
```

---

## 🤖 Bot Features & Usage

### 📱 Add Account
Step-by-step wizard:
1. Enter **API ID** (from https://my.telegram.org → App API)
2. Enter **API Hash**
3. Enter **Phone Number** (e.g. `+919876543210`)
4. Enter the **OTP** sent to your Telegram app
5. _(If 2FA enabled)_ enter your **2FA password**

Session is saved to `sessions/` and auto-reconnects on restart.

---

### 📝 Add Message
- Type or **forward** any message to the bot
- Choose which accounts will send this message
- Supports "All Accounts" option

---

### ▶️ Start Forwarding
- Pick a saved message
- Bot starts sending it to **every group** each chosen account is a member of
- Repeats in a loop, with delay between each send

---

### ⏹ Stop Forwarding
- Stop one account or **all** at once
- Shows how many messages were sent per account

---

### ⏱ Edit Delay
- Set seconds between sending to each group
- Minimum: 5 seconds
- Recommended: 30–60 seconds to avoid Telegram flood limits

---

### 📊 Status
Live dashboard showing:
- Each account's connection status and forwarding state
- Message count
- Active session count
- Current delay setting

---

## 🚀 Deploy on a VM (Linux)

```bash
# Clone or upload your files, then:
sudo apt update && sudo apt install python3 python3-pip -y
pip3 install -r requirements.txt

# Run in background with screen
screen -S marketbot
python3 bot.py
# Press Ctrl+A then D to detach

# Or use systemd (recommended for production):
```

**systemd service** (`/etc/systemd/system/marketbot.service`):
```ini
[Unit]
Description=Telegram Marketing Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/marketing_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable marketbot
sudo systemctl start marketbot
sudo systemctl status marketbot
```

---

## ⚙️ Error Handling

| Error | Auto-handling |
|-------|--------------|
| FloodWaitError | Waits the required time, then continues |
| PeerFloodError | Pauses 60 seconds |
| ChatWriteForbiddenError | Skips that group, continues |
| UserBannedInChannelError | Skips that group, continues |
| Session expired | Shows 🔴 in status, remove and re-add account |

---

## ⚠️ Important Notes

- Always use a reasonable delay (30s+) to avoid Telegram rate limits
- Telegram may restrict accounts that send too many messages — use responsibly
- Each session file is tied to one Telegram account
- Sessions survive bot restarts automatically
