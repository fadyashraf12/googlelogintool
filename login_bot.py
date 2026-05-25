"""
Screen-based Google login automation.
Controls the REAL browser window via xdotool (mouse + keyboard),
so all sessions are saved in the user's actual browser profile.
"""

import os
import subprocess
import time
import random
import math
import traceback
import pyotp

from database import update_account_status
import config


# ── xdotool helpers ──────────────────────────────────────────────────────────

def _env():
    e = os.environ.copy()
    e.setdefault("DISPLAY", ":99")
    return e

def _xdo(*args):
    return subprocess.run(
        ["xdotool"] + list(args),
        capture_output=True, text=True, env=_env()
    )

def _xclip_write(text):
    """Put text into clipboard so we can paste it (handles special chars)."""
    subprocess.run(
        ["xclip", "-selection", "clipboard"],
        input=text, text=True, env=_env()
    )

def find_browser_window():
    """
    Return the XID of any visible browser window the user has open.
    Searches by window class (most reliable), then by title keywords.
    Supports Chrome, Firefox, Brave, Edge, Opera, Vivaldi, Chromium, etc.
    """
    # Search by WM_CLASS — works for all major browsers
    class_patterns = [
        "Google-chrome", "google-chrome",
        "Chromium", "chromium",
        "Firefox", "firefox", "Navigator",
        "Brave-browser", "brave-browser",
        "Microsoft-edge", "microsoft-edge",
        "Opera", "opera",
        "Vivaldi", "vivaldi",
        "Epiphany",  # GNOME Web
    ]
    for cls in class_patterns:
        r = _xdo("search", "--onlyvisible", "--class", cls)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[-1].strip()

    # Fallback: search by window name/title
    for pattern in ["Google Chrome", "Chromium", "Mozilla Firefox",
                    "Brave", "Microsoft Edge", "Opera"]:
        r = _xdo("search", "--onlyvisible", "--name", pattern)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[-1].strip()

    return None

def get_window_title(wid):
    r = _xdo("getwindowname", wid)
    return r.stdout.strip() if r.returncode == 0 else ""

def get_screen_size():
    r = _xdo("getdisplaygeometry")
    if r.returncode == 0:
        parts = r.stdout.strip().split()
        try:
            return int(parts[0]), int(parts[1])
        except Exception:
            pass
    return 1280, 900

def focus_window(wid):
    _xdo("windowfocus", "--sync", wid)
    _xdo("windowraise", wid)
    time.sleep(0.4)

def key(*keys):
    _xdo("key", "--clearmodifiers", *keys)

def paste_text(text):
    """Type text by setting clipboard and pressing Ctrl+A, Ctrl+V."""
    _xclip_write(text)
    time.sleep(0.15)
    key("ctrl+v")

def human_type(text, stop_event=None):
    """Type text character by character with random human-like delays."""
    speed = config.load().get("typing_speed", "normal")
    profiles = {"slow": (100, 220), "normal": (40, 130), "fast": (20, 70)}
    lo, hi = profiles.get(speed, (40, 130))
    typo_rate = config.get_typo_rate()

    for ch in text:
        if stop_event and stop_event.is_set():
            return
        # Occasional typo simulation
        if random.random() < typo_rate:
            wrong = random.choice("abcdefghijklmnop")
            _xdo("type", "--clearmodifiers", "--delay",
                 str(random.randint(lo, hi)), wrong)
            time.sleep(random.uniform(0.08, 0.18))
            key("BackSpace")
            time.sleep(random.uniform(0.05, 0.12))
        _xdo("type", "--clearmodifiers", "--delay",
             str(random.randint(lo, hi)), ch)


def human_mouse_move(x, y, steps=None):
    """Move the mouse in a curved path to (x, y)."""
    if steps is None:
        steps = random.randint(15, 30)
    # Get current position
    r = _xdo("getmouselocation", "--shell")
    cx, cy = 640, 450
    for line in r.stdout.splitlines():
        if line.startswith("X="):
            cx = int(line.split("=")[1])
        elif line.startswith("Y="):
            cy = int(line.split("=")[1])

    # Bezier curve from current to target
    # Control points with slight randomness
    cp1x = cx + (x - cx) * 0.3 + random.uniform(-40, 40)
    cp1y = cy + (y - cy) * 0.1 + random.uniform(-40, 40)
    cp2x = cx + (x - cx) * 0.7 + random.uniform(-40, 40)
    cp2y = cy + (y - cy) * 0.9 + random.uniform(-40, 40)

    for i in range(steps + 1):
        t = i / steps
        bx = (1-t)**3*cx + 3*(1-t)**2*t*cp1x + 3*(1-t)*t**2*cp2x + t**3*x
        by = (1-t)**3*cy + 3*(1-t)**2*t*cp1y + 3*(1-t)*t**2*cp2y + t**3*y
        _xdo("mousemove", str(int(bx)), str(int(by)))
        time.sleep(random.uniform(0.005, 0.018))


def human_click(x, y):
    human_mouse_move(x, y)
    time.sleep(random.uniform(0.08, 0.2))
    _xdo("click", "1")
    time.sleep(random.uniform(0.05, 0.15))


# ── Stop / sleep helpers ─────────────────────────────────────────────────────

def check_stop(stop_event):
    return bool(stop_event and stop_event.is_set())

def isleep(seconds, stop_event=None):
    """Interruptible sleep — returns True if stopped."""
    steps = int(seconds * 10)
    for _ in range(steps):
        if check_stop(stop_event):
            return True
        time.sleep(0.1)
    return check_stop(stop_event)


# ── Page state detection ─────────────────────────────────────────────────────

def _title_contains(wid, *keywords):
    title = get_window_title(wid).lower()
    return any(kw.lower() in title for kw in keywords)

def _wait_for_title_change(wid, old_title, timeout=10, stop_event=None):
    """Wait until window title changes from old_title. Returns new title."""
    for _ in range(timeout * 4):
        if check_stop(stop_event):
            return None
        new = get_window_title(wid)
        if new != old_title:
            return new
        time.sleep(0.25)
    return get_window_title(wid)


# ── Core login flow ──────────────────────────────────────────────────────────

def login_single_screen(wid, email, password,
                        twofa_enabled, twofa_type, totp_secret,
                        log, stop_event):
    """
    Log in to one Google account by controlling the browser window
    via mouse and keyboard (xdotool). Sessions are saved in the real
    browser profile — nothing is isolated.
    """
    W, H = get_screen_size()
    cx = W // 2

    focus_window(wid)

    # ── Open new tab ──────────────────────────────────────────────────────
    key("ctrl+t")
    if isleep(0.9, stop_event): return "STOPPED"

    # ── Navigate to Google login ──────────────────────────────────────────
    key("ctrl+l")
    time.sleep(0.25)
    key("ctrl+a")
    time.sleep(0.1)
    _xdo("type", "--clearmodifiers", "--delay", "30",
         "https://accounts.google.com/signin/v2/identifier")
    key("Return")
    log("  → Navigating to Google login page...")
    if isleep(3.5, stop_event): return "STOPPED"

    # Dismiss any cookie/GDPR overlay
    key("Escape")
    time.sleep(0.3)

    # ── Enter email ───────────────────────────────────────────────────────
    # Google auto-focuses the email field — just type directly.
    # As a safety measure, click roughly where the input sits.
    title_before = get_window_title(wid)
    human_click(cx, int(H * 0.46))
    time.sleep(0.3)

    log(f"  → Entering email...")
    # Use clipboard paste for reliability (handles special chars, faster)
    paste_text(email)
    time.sleep(0.3)
    key("Return")

    # ── Wait for password page ────────────────────────────────────────────
    log("  → Waiting for password field...")
    if isleep(3, stop_event): return "STOPPED"

    # ── Enter password ────────────────────────────────────────────────────
    # Google auto-focuses the password field after email step.
    human_click(cx, int(H * 0.46))
    time.sleep(0.3)

    log("  → Entering password...")
    paste_text(password)
    time.sleep(0.3)
    key("Return")

    # ── Wait for result ───────────────────────────────────────────────────
    log("  → Submitted — waiting for result...")
    if isleep(4, stop_event): return "STOPPED"

    title = get_window_title(wid).lower()

    # ── Handle 2FA ────────────────────────────────────────────────────────
    if twofa_enabled and ("verify" in title or "2-step" in title
                          or "challenge" in title or "sign in" in title):
        if twofa_type == "Authenticator" and totp_secret:
            code = pyotp.TOTP(totp_secret).now()
            log(f"  → 2FA (TOTP) — entering code {code}...")
            human_click(cx, int(H * 0.46))
            time.sleep(0.3)
            _xdo("type", "--clearmodifiers", "--delay", "80", code)
            key("Return")
            if isleep(4, stop_event): return "STOPPED"

        elif twofa_type in ("SMS", "Email", "Google Prompt"):
            log(f"  → 2FA ({twofa_type}) — waiting for manual verification...")
            timeout = config.get_twofa_timeout()
            prev_title = get_window_title(wid)
            for _ in range(timeout):
                if check_stop(stop_event): return "STOPPED"
                time.sleep(1)
                cur = get_window_title(wid).lower()
                if "verify" not in cur and "2-step" not in cur \
                        and "challenge" not in cur and cur != prev_title.lower():
                    break
            else:
                return "2FA_TIMEOUT"

    # ── Detect final state ────────────────────────────────────────────────
    title = get_window_title(wid).lower()

    if "wrong" in title or "incorrect" in title:
        return "WRONG_PASSWORD"
    if "disabled" in title or "suspended" in title:
        return "ACCOUNT_DISABLED"
    if "blocked" in title or "captcha" in title or "unusual" in title:
        return "BLOCKED_OR_CAPTCHA"
    # Still on sign-in page = something went wrong
    if "sign in" in title and "google" in title:
        return "WRONG_PASSWORD"

    return "SUCCESS"


# ── Main entry point ─────────────────────────────────────────────────────────

def login_accounts(accounts, log_callback=None, stop_event=None):
    """
    Find the open browser window and sequentially log in each account
    using mouse and keyboard screen automation.
    """
    log = log_callback or print

    wid = find_browser_window()
    if not wid:
        log("✘ No browser window found.")
        log("  Please click 'Launch Chrome' first, then try again.")
        return

    log(f"✔ Browser window found. Starting screen automation...")

    total = len(accounts)
    for idx, acc in enumerate(accounts, start=1):
        if check_stop(stop_event):
            log("⏹ Automation stopped by user.")
            break

        padded = tuple(acc) + (None,) * 12
        (account_id, email, password, twofa_enabled,
         twofa_type, country_code, phone_number,
         totp_secret, *_) = padded

        log("─" * 50)
        log(f"[{idx}/{total}] Logging in: {email}")
        update_account_status(account_id, "LOGGING_IN")

        # Re-find window each iteration in case it changed
        wid = find_browser_window() or wid

        try:
            status = login_single_screen(
                wid, email, password,
                bool(twofa_enabled),
                twofa_type or "None",
                totp_secret,
                log, stop_event
            )
        except Exception:
            log("  ✗ Unexpected error:")
            log(traceback.format_exc())
            status = "ERROR"

        update_account_status(account_id, status)

        if status == "SUCCESS":
            log(f"  ✓ [{email}] → SUCCESS")
        elif status == "STOPPED":
            log(f"  ⏹ [{email}] → Stopped.")
            break
        else:
            log(f"  ✗ [{email}] → {status}")

        if idx < total and not check_stop(stop_event):
            gap_min, gap_max = config.get_account_gap()
            gap = random.uniform(gap_min, gap_max)
            log(f"  Waiting {gap:.1f}s before next account...")
            isleep(gap, stop_event)

    log("─" * 50)
    log("✔ All accounts processed.")
