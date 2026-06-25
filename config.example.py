# ─────────────────────────────────────────────────────────────────────────────
#  Copy this file to config.py and fill in your values.
#  config.py is gitignored — your secrets will never be committed.
# ─────────────────────────────────────────────────────────────────────────────

# Part of the game window title (case-insensitive, partial match is fine)
WINDOW_TITLE = "Your Game Window Title Here"

# Pixel region to crop from the window: (left, top, right, bottom)
# These coordinates depend on your monitor resolution and game window size — everyone needs to find their own.
# Run: python game_monitor.py --find-crop
# It saves debug_capture.png so you can look up the exact pixel coordinates of the bar.
CROP_BOX = (0, 0, 1920, 80)

# Seconds between checks
POLL_INTERVAL = 3

# Discord bot token — from discord.com/developers
BOT_TOKEN = "your-bot-token-here"

# Your Discord user ID — Settings > Advanced > Developer Mode > right-click yourself > Copy ID
YOUR_DISCORD_USER_ID = 123456789012345678

# Minutes of no bar change before a disconnect alert fires
STUCK_TIMEOUT_MINS = 25

