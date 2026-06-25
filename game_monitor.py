"""
Game Notification Monitor
=========================
Watches a region of a game window for text changes and sends categorised
Discord DM notifications — works even when the game is on a different
virtual desktop / macOS Space, or the window is minimised.

Quick start:
  1. Copy config.example.py → config.py and fill in your values
  2. pip install -r requirements.txt          (platform-specific — see file)
  3. python game_monitor.py --find-crop       (find your crop box)
  4. python game_monitor.py --test            (test Discord connection)
  5. python game_monitor.py --test-ocr        (test OCR reads your bar)
  6. python game_monitor.py                   (run normally)
"""

import ctypes
import datetime
import difflib
import hashlib
import io
import json
import pathlib
import re
import string
import sys
import time
import argparse
import platform as _platform

_here = pathlib.Path(__file__).parent

import requests
from PIL import Image

_PUNCT = string.punctuation

# ── Platform detection ────────────────────────────────────────────────────────
_OS = _platform.system()   # "Windows" or "Darwin"

if _OS == "Windows":
    import win32gui
    import win32ui
elif _OS == "Darwin":
    try:
        import Quartz
    except ImportError:
        print("ERROR: Quartz not found. Run: pip install pyobjc-framework-Quartz")
        sys.exit(1)
else:
    print(f"ERROR: Unsupported platform: {_OS}")
    sys.exit(1)

# ── Load config ───────────────────────────────────────────────────────────────
try:
    import config
except ModuleNotFoundError:
    print("ERROR: config.py not found.")
    print("Copy config.example.py to config.py and fill in your values.")
    sys.exit(1)

_easyocr_reader = None
def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        print("[OCR] Loading EasyOCR model (first run only)...")
        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        print("[OCR] EasyOCR ready.")
    return _easyocr_reader


# ═══════════════════════════════════════════════════════════════════════════════
#  CATEGORIES
#  Checked top-to-bottom; first keyword match wins.
#  Named events (events.json) are checked before these.
# ═══════════════════════════════════════════════════════════════════════════════

DISCONNECT_KEYWORDS = [
    "disconnected", "inactivity", "you have been removed",
    "session ended", "timed out", "kicked",
]

CATEGORIES = [
    {
        "id":       "disconnect",
        "name":     "🔌 Disconnected",
        "color":    0xE74C3C,
        "keywords": DISCONNECT_KEYWORDS,
        "ping":     True,
    },
]

SEVERITY_COLORS = {"high": 0xE74C3C, "medium": 0xF39C12, "low": 0x9B59B6}
SEVERITY_EMOJI  = {"high": "🔴",     "medium": "🟡",      "low": "🟢"}

# Sent when text appears but matches no known event or category keyword.
# A screenshot of the bar is attached so you can read what OCR captured
# and add a pattern to events.json if needed.
UNKNOWN_CAT = {
    "id":    "unknown",
    "name":  "❓ Unknown Event",
    "color": 0x7F8C8D,
    "ping":  False,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  EVENTS  (events.json)
#
#  Each entry supports:
#    "keywords" : ["exact", "substrings"]          — plain substring match
#    "pattern"  : "regex with .* wildcards"        — compiled regex match
#  Either or both can be present; pattern is tried first if present.
# ═══════════════════════════════════════════════════════════════════════════════

def load_events():
    try:
        with open(_here / "events.json", encoding="utf-8") as f:
            events = json.load(f).get("events", [])
        # Pre-compile regex patterns
        for ev in events:
            raw = ev.get("pattern")
            ev["_pattern"] = re.compile(raw, re.IGNORECASE) if raw else None
        return events
    except FileNotFoundError:
        print("[WARN] events.json not found — event matching disabled.")
        return []
    except (json.JSONDecodeError, re.error) as e:
        print(f"[ERROR] Could not load events.json: {e}")
        return []


def _fuzzy_ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

# How similar OCR text needs to be to an effect string to count as a match.
# 0.70 means 70% of characters match — tolerates typical OCR errors.
# Raise it (e.g. 0.85) to be stricter; lower it (e.g. 0.55) to be more lenient.
FUZZY_THRESHOLD = getattr(config, "FUZZY_THRESHOLD", 0.70)

def _event_matches_exact(event, lower_text):
    """Match by regex pattern or keywords only — no fuzzy."""
    pat = event.get("_pattern")
    if pat and pat.search(lower_text):
        return True
    if any(kw.lower() in lower_text for kw in event.get("keywords", [])):
        return True
    return False


def _event_matches_fuzzy(event, lower_text):
    """Fuzzy fallback — only used when no exact match found across all events."""
    effect = event.get("effect", "").lower()
    return bool(effect and _fuzzy_ratio(lower_text, effect) >= FUZZY_THRESHOLD)


def classify(text):
    """
    Returns (category_dict, event_detail_or_None).
    Priority: disconnect → events.json exact → events.json fuzzy → CATEGORIES keywords → general fallback.
    Fuzzy matching only runs if no event matched by regex/keywords first.
    """
    lower = text.lower()

    if any(kw in lower for kw in DISCONNECT_KEYWORDS):
        return CATEGORIES[0], None

    events = load_events()

    # Pass 1: regex / keyword matches only
    for event in events:
        if _event_matches_exact(event, lower):
            sev = event.get("severity", "low")
            event_cat = {
                "id":    "event",
                "name":  "🎉 Event",
                "color": SEVERITY_COLORS.get(sev, 0x9B59B6),
                "ping":  sev == "high",
            }
            return event_cat, event

    # Pass 2: fuzzy only — pick the highest-ratio match, not the first
    best_event, best_ratio = None, 0.0
    for event in events:
        effect = event.get("effect", "").lower()
        if effect:
            ratio = _fuzzy_ratio(lower, effect)
            if ratio > best_ratio:
                best_ratio = ratio
                best_event = event
    if best_event and best_ratio >= FUZZY_THRESHOLD:
        sev = best_event.get("severity", "low")
        event_cat = {
            "id":    "event",
            "name":  "🎉 Event",
            "color": SEVERITY_COLORS.get(sev, 0x9B59B6),
            "ping":  sev == "high",
        }
        return event_cat, best_event

    for cat in CATEGORIES:
        if any(kw in lower for kw in cat["keywords"]):
            return cat, None

    # Nothing matched — mark as unknown so the caller can attach a screenshot
    return UNKNOWN_CAT, None


# ═══════════════════════════════════════════════════════════════════════════════
#  DISCORD
# ═══════════════════════════════════════════════════════════════════════════════

_dm_channel_id = None


def get_dm_channel():
    global _dm_channel_id
    if _dm_channel_id:
        return _dm_channel_id
    r = requests.post(
        "https://discord.com/api/v10/users/@me/channels",
        headers={
            "Authorization": f"Bot {config.BOT_TOKEN}",
            "Content-Type":  "application/json",
        },
        json={"recipient_id": config.YOUR_DISCORD_USER_ID},
        timeout=10,
    )
    r.raise_for_status()
    _dm_channel_id = r.json()["id"]
    return _dm_channel_id


def build_embed(text, cat, event_detail=None, attach_image=False):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if event_detail:
        sev = event_detail.get("severity", "low")
        embed = {
            "title":       f"🎉 {event_detail['name']}",
            "description": f"> {text}",
            "color":       SEVERITY_COLORS.get(sev, 0x9B59B6),
            "fields": [
                {"name": "Effect",   "value": event_detail.get("effect", "—"), "inline": False},
                {"name": "Severity", "value": f"{SEVERITY_EMOJI.get(sev, '')} {sev.capitalize()}", "inline": True},
            ],
            "footer":    {"text": "Game Monitor"},
            "timestamp": now_iso,
        }
    else:
        embed = {
            "title":       cat["name"],
            "description": f"> {text}" if text else "*OCR returned no text — see attached image*",
            "color":       cat["color"],
            "footer":      {"text": "Game Monitor"},
            "timestamp":   now_iso,
        }

    if attach_image:
        embed["image"] = {"url": "attachment://bar_capture.png"}

    return embed


def send_notification(text, cat, event_detail=None, image=None):
    try:
        channel_id = get_dm_channel()
        embed      = build_embed(text, cat, event_detail, attach_image=image is not None)
        payload    = {"embeds": [embed]}

        if cat.get("ping"):
            payload["content"] = f"<@{config.YOUR_DISCORD_USER_ID}>"

        url     = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bot {config.BOT_TOKEN}"}

        if image is not None:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)
            r = requests.post(
                url, headers=headers,
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": ("bar_capture.png", buf, "image/png")},
                timeout=10,
            )
        else:
            headers["Content-Type"] = "application/json"
            r = requests.post(url, headers=headers, json=payload, timeout=10)

        r.raise_for_status()
        print(f"  ✓ [{cat['name']}] {text[:80]}")

    except requests.RequestException as e:
        print(f"  ✗ Discord error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  WINDOW CAPTURE — Windows
# ═══════════════════════════════════════════════════════════════════════════════

def _find_window_win(partial_title):
    matches = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if title and partial_title.lower() in title.lower():
            matches.append((hwnd, title))

    win32gui.EnumWindows(cb, None)
    return matches[0] if matches else (None, None)


def _capture_window_win(wid, crop):
    """PrintWindow — renders even when minimised or on another virtual desktop."""
    left, top, right, bottom = win32gui.GetWindowRect(wid)
    w, h = right - left, bottom - top

    if w <= 0 or h <= 0:
        return None

    hwnd_dc = win32gui.GetWindowDC(wid)
    mfc_dc  = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bmp     = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bmp)

    result = ctypes.windll.user32.PrintWindow(wid, save_dc.GetSafeHdc(), 2)  # PW_RENDERFULLCONTENT

    info = bmp.GetInfo()
    bits = bmp.GetBitmapBits(True)
    img  = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits, "raw", "BGRX", 0, 1)

    win32gui.DeleteObject(bmp.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(wid, hwnd_dc)

    if result != 1:
        return None

    clamped = (max(0, crop[0]), max(0, crop[1]), min(w, crop[2]), min(h, crop[3]))
    return img.crop(clamped)


def _list_windows_win():
    print("All visible windows:")
    win32gui.EnumWindows(
        lambda h, _: print(f"  {win32gui.GetWindowText(h)!r}") if win32gui.GetWindowText(h) else None,
        None,
    )


def _window_size_win(wid):
    left, top, right, bottom = win32gui.GetWindowRect(wid)
    return right - left, bottom - top


# ═══════════════════════════════════════════════════════════════════════════════
#  WINDOW CAPTURE — macOS
# ═══════════════════════════════════════════════════════════════════════════════

def _find_window_mac(partial_title):
    wlist = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    key = partial_title.lower()
    # Collect owner-name matches and tab-title-only matches separately.
    # Owner matches (the app itself is the game) beat tab-title matches (a browser with the game open).
    owner_best, owner_area = None, 0
    title_best, title_area = None, 0
    for w in (wlist or []):
        owner = w.get("kCGWindowOwnerName", "") or ""
        name  = w.get("kCGWindowName",      "") or ""
        b     = w.get("kCGWindowBounds", {})
        area  = int(b.get("Width", 0)) * int(b.get("Height", 0))
        if key in owner.lower():
            if area > owner_area:
                owner_best, owner_area = (w.get("kCGWindowNumber"), owner or name), area
        elif key in name.lower():
            if area > title_area:
                title_best, title_area = (w.get("kCGWindowNumber"), owner or name), area
    return owner_best or title_best or (None, None)


def _capture_window_mac(wid, crop):
    """CGWindowListCreateImage — works across macOS Spaces regardless of focus."""
    cg_img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        wid,
        Quartz.kCGWindowImageBoundsIgnoreFraming,
    )
    if not cg_img:
        return None

    width  = Quartz.CGImageGetWidth(cg_img)
    height = Quartz.CGImageGetHeight(cg_img)
    bpr    = width * 4
    buf    = (ctypes.c_uint8 * (bpr * height))()
    cs     = Quartz.CGColorSpaceCreateDeviceRGB()

    ctx = Quartz.CGBitmapContextCreate(
        buf, width, height, 8, bpr, cs,
        Quartz.kCGImageAlphaNoneSkipFirst | Quartz.kCGBitmapByteOrder32Little,
    )
    Quartz.CGContextDrawImage(ctx, Quartz.CGRectMake(0, 0, width, height), cg_img)

    # Memory layout: B G R X per pixel (32-bit little-endian, alpha skipped)
    img = Image.frombytes("RGB", (width, height), bytes(buf), "raw", "BGRX")

    w, h = img.size
    clamped = (max(0, crop[0]), max(0, crop[1]), min(w, crop[2]), min(h, crop[3]))
    return img.crop(clamped)


def _list_windows_mac():
    wlist = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    seen = set()
    print("All application windows (including other Spaces):")
    for w in (wlist or []):
        owner = w.get("kCGWindowOwnerName", "") or ""
        name  = w.get("kCGWindowName",      "") or ""
        key   = owner
        if owner and key not in seen:
            seen.add(key)
            print(f"  {owner!r}" + (f"  —  {name!r}" if name else ""))


def _window_size_mac(wid):
    wlist = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
    for w in (wlist or []):
        if w.get("kCGWindowNumber") == wid:
            b = w.get("kCGWindowBounds", {})
            return int(b.get("Width", 0)), int(b.get("Height", 0))
    return 0, 0


# ═══════════════════════════════════════════════════════════════════════════════
#  UNIFIED WINDOW API
# ═══════════════════════════════════════════════════════════════════════════════

def find_window(partial_title):
    return _find_window_mac(partial_title) if _OS == "Darwin" else _find_window_win(partial_title)


def capture_window(wid, crop):
    return _capture_window_mac(wid, crop) if _OS == "Darwin" else _capture_window_win(wid, crop)


def inner_img(img, inset=8):
    """Strip border pixels before hashing so border glow/animation doesn't cause false triggers."""
    w, h = img.size
    return img.crop((inset, inset, w - inset, h - inset))


def _preprocess(img):
    from PIL import ImageEnhance
    w, h = img.size
    img = img.resize((w * 2, h * 2), Image.LANCZOS)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img


def read_text(img):
    import numpy as np
    arr = np.array(_preprocess(img))
    reader = _get_easyocr_reader()
    results = reader.readtext(arr, detail=1, paragraph=False)
    if not results:
        return ""
    results.sort(key=lambda r: r[0][0][0])
    return " ".join(r[1] for r in results).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS (--find-crop, --test, --test-ocr)
# ═══════════════════════════════════════════════════════════════════════════════

def cmd_find_crop():
    print(f"Searching for window: '{config.WINDOW_TITLE}'...\n")
    wid, title = find_window(config.WINDOW_TITLE)

    if not wid:
        print(f"No window found matching '{config.WINDOW_TITLE}'")
        print()
        if _OS == "Darwin":
            _list_windows_mac()
        else:
            _list_windows_win()
        return

    if _OS == "Darwin":
        w, h = _window_size_mac(wid)
    else:
        w, h = _window_size_win(wid)

    print(f"Found:       {title!r}")
    print(f"Window size: {w} x {h}")
    print(f"\nSuggested CROP_BOX for a top bar: (0, 0, {w}, 100)")
    print("Adjust the last number (height) to match your bar.\n")

    img = capture_window(wid, (0, 0, w, h))
    if img:
        img.save("debug_capture.png")
        print("Full window saved as debug_capture.png")
        print("Open it, find the pixel coordinates of your bar, then update CROP_BOX in config.py")
    else:
        print("Capture failed — try running the game in windowed or borderless windowed mode.")


_TEST_HIGH_CAT = {
    "id": "test", "name": "⚠️ Test Alert", "color": 0xE74C3C, "ping": True,
}

def cmd_test_discord():
    print("Sending three test messages to your Discord DMs...\n")
    send_notification("Test — general notification (no ping).", UNKNOWN_CAT)
    time.sleep(1)
    send_notification("Test — high severity alert (you should be pinged).", _TEST_HIGH_CAT)
    time.sleep(1)
    send_notification("Test — named event with detail.", _TEST_HIGH_CAT, {
        "name":     "Test Event",
        "effect":   "Sample effect description.",
        "severity": "high",
    })
    print("\nDone — check your Discord DMs.")


def cmd_test_ocr():
    print(f"Capturing '{config.WINDOW_TITLE}' and running OCR...\n")
    wid, title = find_window(config.WINDOW_TITLE)

    if not wid:
        print(f"Window not found: '{config.WINDOW_TITLE}'")
        return

    img = capture_window(wid, config.CROP_BOX)
    if img is None:
        print("Capture failed.")
        return

    img.save("debug_bar.png")
    text = read_text(img)

    print(f"Window:     {title!r}")
    print(f"OCR result: {text!r}")
    print("\nBar image saved as debug_bar.png")

    if text:
        cat, event = classify(text)
        print(f"Classified: {cat['name']}" + (f" → {event['name']}" if event else ""))
    else:
        print("OCR returned empty text — check debug_bar.png to see what was captured.")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  Game Monitor")
    print(f"  Platform: {_OS}")
    print(f"  Window:   {config.WINDOW_TITLE!r}")
    print(f"  Crop:     {config.CROP_BOX}")
    print(f"  Interval: {config.POLL_INTERVAL}s")
    print("=" * 55)

    last_img_hash       = ""
    last_event_key      = None   # resets on bar clear; dedupes consecutive same-event fires
    last_game_event     = None   # last EVENT: that fired; persists through bar clears
    last_change_at      = datetime.datetime.now(datetime.timezone.utc)
    stuck_notified      = False
    event_cooldowns: dict = {}   # non-EVENT: key -> last notified datetime
    last_known_event_active = False  # True once a known event fires; reset when bar clears
    last_unknown_fired      = False  # True once an unknown fires; reset when bar clears
    consecutive_empty_reads = 0     # guard against brief OCR blanks resetting active-event state

    while True:
        wid, _ = find_window(config.WINDOW_TITLE)

        if not wid:
            print(f"[{_ts()}] Window not found — retrying in 5s...")
            time.sleep(5)
            continue

        img = capture_window(wid, config.CROP_BOX)
        if img is None:
            time.sleep(config.POLL_INTERVAL)
            continue

        img_hash = hashlib.md5(inner_img(img).tobytes()).hexdigest()
        now      = datetime.datetime.now(datetime.timezone.utc)

        if img_hash == last_img_hash:
            # Bar unchanged — only check stuck timer
            mins = (now - last_change_at).total_seconds() / 60
            if mins >= config.STUCK_TIMEOUT_MINS and not stuck_notified:
                print(f"[{_ts()}] Bar unchanged for {int(mins)}m — sending disconnect alert")
                send_notification(
                    f"No changes detected for {int(mins)} minutes. Possible disconnect or inactivity kick.",
                    CATEGORIES[0],
                )
                stuck_notified = True
            time.sleep(config.POLL_INTERVAL)
            continue

        # Bar changed — reset stuck timer and process
        last_img_hash  = img_hash
        last_change_at = now
        stuck_notified = False

        text = read_text(img)
        if not text or len(text.strip()) < 4:
            # Could be a true bar clear OR a single-frame OCR blank during animation.
            # Require 3 consecutive empty reads before resetting state so a brief OCR
            # miss doesn't allow unknowns to fire while the same event is still active.
            consecutive_empty_reads += 1
            if consecutive_empty_reads >= 3:
                last_event_key          = None
                last_known_event_active = False
                last_unknown_fired      = False
            time.sleep(config.POLL_INTERVAL)
            continue

        consecutive_empty_reads = 0  # valid text — bar is still populated

        # Reject garbage: >50% alphanumeric, ≥3 alpha words (len≥2), AND ≥2 substantial words (len≥5)
        # "___ Appears" messages are short by design — lower thresholds to 2 words / 1 long word.
        stripped = text.replace(" ", "")
        alpha_ratio = sum(c.isalnum() for c in stripped) / len(stripped) if stripped else 0
        real_words = [w.strip(_PUNCT) for w in text.split()]
        real_words = [w for w in real_words if w.isalpha() and len(w) >= 2]
        long_words = [w for w in real_words if len(w) >= 5]
        is_appears_msg = "appears" in text.lower()
        min_words = 2 if is_appears_msg else 3
        min_long  = 1 if is_appears_msg else 2
        if alpha_ratio < 0.5 or len(real_words) < min_words or len(long_words) < min_long:
            time.sleep(config.POLL_INTERVAL)
            continue

        cat, event_detail = classify(text)

        # Event identity, independent of countdown numbers / color shifts in the pixels:
        #   known event  -> its name      (e.g. "Mine Reset")
        #   category      -> its id        (e.g. "disconnect")
        #   unknown       -> the OCR text  (best we can do without a defined event)
        if event_detail:
            event_key = event_detail["name"]
        elif cat["id"] == "unknown":
            event_key = text
        else:
            event_key = cat["id"]

        if event_key == last_event_key:
            time.sleep(config.POLL_INTERVAL)
            continue

        # For unknowns, OCR varies slightly each poll — treat as repeat if text is similar enough
        if cat["id"] == "unknown" and last_event_key is not None:
            if _fuzzy_ratio(event_key, last_event_key) >= FUZZY_THRESHOLD:
                time.sleep(config.POLL_INTERVAL)
                continue

        if event_key.startswith("EVENT:"):
            # EVENT: entries: no time cooldown — just suppress if same event already sent
            if event_key == last_game_event:
                time.sleep(config.POLL_INTERVAL)
                continue
            last_game_event = event_key
        else:
            # Notif/other entries: short cooldown to absorb brief bar flickers
            cooldown_secs = getattr(config, "EVENT_COOLDOWN_SECS", 6)
            last_fired = event_cooldowns.get(event_key)
            if last_fired and (now - last_fired).total_seconds() < cooldown_secs:
                time.sleep(config.POLL_INTERVAL)
                continue
            event_cooldowns[event_key] = now

        # Suppress unknown re-fires for the same bar session:
        #   - known event already identified → all subsequent unknowns are OCR noise
        #   - unknown already sent → don't spam; wait for bar to clear or OCR to identify it
        # Known events are never suppressed — if OCR finally identifies after an unknown, it fires.
        # "___ Appears" messages are always allowed through — they're a distinct bar state,
        # not OCR noise from an already-identified event.
        if cat["id"] == "unknown" and not is_appears_msg and (last_known_event_active or last_unknown_fired):
            time.sleep(config.POLL_INTERVAL)
            continue

        last_event_key = event_key
        print(f"[{_ts()}] {text[:100]}")
        attach = img if cat["id"] == "unknown" else None
        send_notification(text, cat, event_detail, image=attach)
        if cat["id"] == "unknown":
            last_unknown_fired = True
        else:
            last_known_event_active = True

        time.sleep(config.POLL_INTERVAL)


def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S")


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Game notification monitor")
    parser.add_argument("--find-crop", action="store_true", help="Find your window and suggest a crop box")
    parser.add_argument("--test",      action="store_true", help="Send test Discord notifications")
    parser.add_argument("--test-ocr",  action="store_true", help="Capture bar and print OCR result")
    args = parser.parse_args()

    if args.find_crop:
        cmd_find_crop()
    elif args.test:
        cmd_test_discord()
    elif args.test_ocr:
        cmd_test_ocr()
    else:
        main()
