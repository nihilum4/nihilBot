# Game Monitor

Watches the notification bar in REx:R and sends Discord DM alerts. Works when the game is on a different virtual desktop or you're afk, unless the screen closes.

## Features

- Captures the game window using the Windows `PrintWindow` API, no need for the game to be visible or in focus.
- OCR reads the notification bar text with Tesseract
- Classifies notifications: named events, important alerts, resets, disconnects, general
- Named events defined in `events.json` — add as many as you want without touching code
- Discord DM with colour-coded embeds and optional ping for high-priority alerts
- Disconnect detection — alerts you if the bar hasn't changed in N minutes (likely kicked for inactivity)

## Requirements

- Windows 10/11
- Python 3.8+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- A Discord account

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/game-monitor.git
cd game-monitor
pip install -r requirements.txt
```

Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki

### 2. Create your config

```bash
cp config.example.py config.py
```

Open `config.py` and fill in:

| Setting | What it is |
|---|---|
| `WINDOW_TITLE` | Part of your game's window title |
| `CROP_BOX` | Pixel region of the notification bar (see step 4) |
| `BOT_TOKEN` | Your Discord bot token |
| `YOUR_DISCORD_USER_ID` | Your Discord user ID |

### 3. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. New Application → Bot → Reset Token → copy the token
3. Enable **Message Content Intent** on the Bot page
4. OAuth2 → URL Generator → scope `bot` + permission `Send Messages` → open the URL → add bot to a server you're in
5. Get your user ID: Discord Settings → Advanced → Developer Mode → right-click your name → Copy ID

### 4. Find your crop box

```bash
python game_monitor.py --find-crop
```

This saves `debug_capture.png` — a full screenshot of the game window. Open it, note the pixel coordinates of your notification bar, and update `CROP_BOX` in `config.py`.

### 5. Test Discord

```bash
python game_monitor.py --test
```

Check your Discord DMs for three test messages.

### 6. Test OCR

```bash
python game_monitor.py --test-ocr
```

Make sure the game is open and showing something in the bar. The command prints what Tesseract reads and saves `debug_bar.png`.

### 7. Add your events

Edit `events.json` — add an entry for each named event in your game:

```json
{
  "keywords": ["text that appears in the bar"],
  "name": "Event Display Name",
  "effect": "What this event does",
  "severity": "high"
}
```

Severity levels: `high` (red, pings you), `medium` (yellow), `low` (purple)

### 8. Run

```bash
python game_monitor.py
```

Leave it running in the background. It logs every change to the terminal and sends a Discord DM to your phone.

## Notification types

| Type | Colour | Ping |
|---|---|---|
| 🔌 Disconnected | Red | Yes |
| ⚠️ Important | Red | Yes |
| 🎉 Event (high severity) | Red | Yes |
| 🎉 Event (medium severity) | Yellow | No |
| 🎉 Event (low severity) | Purple | No |
| 🔄 Reset | Orange | No |
| 📢 General | Gray | No |

## Troubleshooting

**Window not found** — run `--find-crop` to list all visible windows and find the exact title.

**OCR reads garbage** — run `--test-ocr` and inspect `debug_bar.png`. Make sure `CROP_BOX` captures the full bar. Larger text OCRs better — try windowed mode if the window is small.

**Blank capture** — some games using hardware acceleration (DirectX/Vulkan fullscreen exclusive) block `PrintWindow`. Switch to **borderless windowed** mode.

**Discord 401 error** — your bot token is wrong or was reset. Get a fresh one from the developer portal.
