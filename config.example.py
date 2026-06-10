# ─────────────────────────────────────────────────────────────────────────────
#  Copy this file to config.py and fill in your values.
#  config.py is gitignored — your secrets will never be committed.
# ─────────────────────────────────────────────────────────────────────────────

# Part of the game window title (case-insensitive, partial match is fine)
WINDOW_TITLE = "Your Game Window Title Here"

# Pixel region to crop from the window: (left, top, right, bottom)
# Run python game_monitor.py --find-crop to help figure this out
CROP_BOX = (0, 0, 1920, 80)

# Seconds between checks
POLL_INTERVAL = 3

# Discord bot token — from discord.com/developers
BOT_TOKEN = "your-bot-token-here"

# Your Discord user ID — Settings > Advanced > Developer Mode > right-click yourself > Copy ID
YOUR_DISCORD_USER_ID = 123456789012345678

# Minutes of no bar change before a disconnect alert fires
STUCK_TIMEOUT_MINS = 25

# Uncomment and update if Tesseract is not on your system PATH
# Windows: TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# macOS:   TESSERACT_PATH = "/usr/local/bin/tesseract"   # or: brew --prefix tesseract
