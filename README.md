# nihilBot

Watches the notification bar in REx:R and sends Discord DM alerts. Works when the game is on a different virtual desktop or you're AFK, as long as the screen isn't closed.

## What it does

- Captures the game window in the background — game doesn't need to be visible or focused
- Reads the notification bar text with OCR (Tesseract)
- Sends you a Discord DM with colour-coded alerts for events, resets, and disconnects
- Pings you for high-priority alerts
- Alerts you if the bar hasn't changed in a while (likely disconnected/kicked)

---

## Requirements

- Windows 10 or 11
- Python 3.8 or newer
- A Discord account

---

## Installation

### Step 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest version
2. Run the installer
3. **Important:** On the first screen, check the box that says **"Add Python to PATH"** before clicking Install

To verify it worked, open **Command Prompt** (press `Win + R`, type `cmd`, press Enter) and run:
```
python --version
```
You should see something like `Python 3.12.x`.

---

### Step 2 — Download nihilBot

**Option A — with Git (recommended):**

If you have Git installed, open Command Prompt and run:
```
git clone https://github.com/Shadewing42/nihilBot1.git
cd nihilBot1
```

**Option B — without Git:**

1. Go to the GitHub page for this project
2. Click the green **Code** button → **Download ZIP**
3. Extract the ZIP somewhere (e.g. your Desktop)
4. Open Command Prompt and navigate to the folder:
   ```
   cd C:\Users\YourName\Desktop\nihilBot1
   ```
   Replace `YourName` with your actual Windows username.

---

### Step 3 — Install Python packages

In Command Prompt, while inside the nihilBot1 folder, run:
```
pip install -r requirements.txt
```

---

### Step 4 — Create your config file

In the nihilBot1 folder, find the file called `config.example.py`. Make a copy of it and rename the copy to `config.py`.

You can do this in File Explorer (right-click → Copy, then paste and rename), or in Command Prompt:
```
copy config.example.py config.py
```

Open `config.py` in Notepad or any text editor and fill in these values:

| Setting | What to put |
|---|---|
| `WINDOW_TITLE` | Part of the game's window title (check the taskbar) |
| `CROP_BOX` | Pixel region of the notification bar — see Step 6 below |
| `BOT_TOKEN` | Your Discord bot token — see Step 5 below |
| `YOUR_DISCORD_USER_ID` | Your Discord user ID — see Step 5 below |

---

### Step 5 — Set up a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) and log in
2. Click **New Application**, give it any name, then go to the **Bot** tab on the left
3. Click **Reset Token**, confirm, then copy the token — paste it as your `BOT_TOKEN` in `config.py`
4. On the same Bot page, scroll down to **Privileged Gateway Intents** and enable **Message Content Intent**
5. Go to **OAuth2 → URL Generator**, tick the `bot` scope, then tick the `Send Messages` permission
6. Copy the generated URL, open it in your browser, and add the bot to a server you're in
7. **Get your user ID:** Open Discord → Settings → Advanced → turn on **Developer Mode** → close Settings → right-click your own name anywhere → **Copy User ID** — paste that number as `YOUR_DISCORD_USER_ID` in `config.py`

---

### Step 6 — Find your crop box

**Everyone needs to do this step individually.** The `CROP_BOX` coordinates depend on your monitor resolution and game window size, so the values from someone else's config likely won't work.

Make sure the game is open, then run:
```
python game_monitor.py --find-crop
```

This saves a file called `debug_capture.png` in the nihilBot1 folder — open it. It's a screenshot of the game window. Look at where the notification bar is and note the pixel coordinates of its edges (top, bottom, left, right). Update `CROP_BOX` in `config.py` with those values in the format `(left, top, right, bottom)`.

---

### Step 7 — Test Discord

```
python game_monitor.py --test
```

Check your Discord DMs — you should receive three test messages with different colours.

---

### Step 8 — Test OCR

With the game open and something visible in the notification bar, run:
```
python game_monitor.py --test-ocr
```

This prints what the OCR is reading and saves `debug_bar.png`. If the text looks garbled, your `CROP_BOX` may not be capturing the bar correctly — open `debug_bar.png` and compare it to what you see in-game.

---

### Step 9 — Add your events (optional)

Open `events.json` and add an entry for each named event you want to track:

```json
{
  "keywords": ["text that appears in the bar"],
  "name": "Event Display Name",
  "effect": "What this event does",
  "severity": "high"
}
```

Severity: `high` = red + pings you, `medium` = yellow, `low` = purple

---

### Step 10 — Run it

```
python game_monitor.py
```

Leave the Command Prompt window open in the background. It logs every change to the terminal and sends Discord DMs to your phone.

---

## Notification types

| Type | Colour | Ping |
|---|---|---|
| Disconnected | Red | Yes |
| Important | Red | Yes |
| Event (high) | Red | Yes |
| Event (medium) | Yellow | No |
| Event (low) | Purple | No |
| Reset | Orange | No |
| General | Gray | No |

---

## Troubleshooting

**"python is not recognized"** — Python isn't on your PATH. Reinstall Python and make sure to check "Add Python to PATH" on the first screen.

**Window not found** — run `--find-crop` — it lists all visible windows so you can find the exact title to use for `WINDOW_TITLE`.

**OCR reads garbage** — run `--test-ocr` and open `debug_bar.png`. Make sure `CROP_BOX` fully covers the notification bar. The game running in windowed mode (not fullscreen) usually gives better results.

**Blank/black capture** — some games using fullscreen exclusive mode (DirectX/Vulkan) block the capture. Switch the game to **borderless windowed** mode.

**Discord 401 error** — your bot token is wrong or has been reset. Go back to the Discord developer portal, reset the token, and update `config.py`.
