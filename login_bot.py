"""
Screen automation using pyautogui + pygetwindow.
Works on Windows, macOS, and Linux.
Finds your already-open browser window and controls it
with real mouse movements and keyboard input.
"""

import os
import sys
import time
import random
import traceback
import pyotp

from database import update_account_status
import config

# ── Lazy imports (pyautogui touches X11/Windows on import; defer until needed) ─
_pyautogui = None
_pyperclip  = None

def _pag():
    """Return the pyautogui module, initialising it on first use."""
    global _pyautogui
    if _pyautogui is None:
        import pyautogui as _p
        _p.FAILSAFE = False
        _p.PAUSE = 0
        _pyautogui = _p
    return _pyautogui

def _clip():
    global _pyperclip
    if _pyperclip is None:
        import pyperclip as _pc
        _pyperclip = _pc
    return _pyperclip

# ── Browser keywords ─────────────────────────────────────────────────────────

_BROWSER_KEYWORDS = [
    "chrome", "chromium", "firefox", "brave", "opera",
    "vivaldi", "edge", "google", "mozilla", "internet explorer",
    "safari", "netscape",
]

_IS_WINDOWS = sys.platform == "win32"

# ── Window helpers ───────────────────────────────────────────────────────────

def find_browser_window():
    """
    Return any open browser window, or None.
    Windows → pygetwindow (returns a window object with .activate() etc.)
    Linux   → wmctrl / xdotool (returns a string window ID)
    """
    if _IS_WINDOWS:
        return _find_browser_windows()
    else:
        return _find_browser_linux()


def _find_browser_windows():
    """Windows: use pygetwindow to find a browser window object."""
    try:
        import pygetwindow as gw
        for win in gw.getAllWindows():
            title = (win.title or "").lower()
            if any(kw in title for kw in _BROWSER_KEYWORDS):
                try:
                    if win.isMinimized:
                        win.restore()
                        time.sleep(0.3)
                except Exception:
                    pass
                return win
    except Exception:
        pass
    return None


def _find_browser_linux():
    """Linux: use wmctrl to list all windows, fall back to xdotool."""
    import subprocess
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":99")

    # Method 1: wmctrl -lx — most reliable
    try:
        r = subprocess.run(
            ["wmctrl", "-lx"], capture_output=True, text=True, env=env
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.split(None, 4)
                if len(parts) < 5:
                    continue
                wm_class = parts[2].lower()
                title    = parts[4].lower()
                if any(kw in wm_class or kw in title for kw in _BROWSER_KEYWORDS):
                    try:
                        return str(int(parts[0], 16))
                    except ValueError:
                        return parts[0]
    except FileNotFoundError:
        pass

    # Method 2: xdotool search by class
    for cls in ["Google-chrome", "Chromium", "Firefox", "Navigator",
                "Brave-browser", "Microsoft-edge", "Opera", "Vivaldi"]:
        r = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--class", cls],
            capture_output=True, text=True, env=env
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[-1].strip()

    # Method 3: xdotool search by name
    for pat in ["Chrome", "Chromium", "Firefox", "Brave", "Edge", "Opera"]:
        r = subprocess.run(
            ["xdotool", "search", "--name", pat],
            capture_output=True, text=True, env=env
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().split("\n")[-1].strip()

    return None


class _LinuxWindow:
    """Thin wrapper around an xdotool window ID so focus_window() works uniformly."""
    def __init__(self, wid):
        self._wid = str(wid)
        self.title = _linux_window_title(wid)

    def activate(self):
        import subprocess
        env = os.environ.copy(); env.setdefault("DISPLAY", ":99")
        subprocess.run(["xdotool", "windowfocus", "--sync", self._wid],
                       env=env, capture_output=True)
        subprocess.run(["xdotool", "windowraise", self._wid],
                       env=env, capture_output=True)

    # Geometry — used for click coordinates
    @property
    def left(self):
        return self._geom()[0]
    @property
    def top(self):
        return self._geom()[1]
    @property
    def width(self):
        return self._geom()[2]
    @property
    def height(self):
        return self._geom()[3]

    def _geom(self):
        try:
            import subprocess
            env = os.environ.copy(); env.setdefault("DISPLAY", ":99")
            r = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", self._wid],
                capture_output=True, text=True, env=env
            )
            g = {}
            for line in r.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    g[k.strip()] = int(v.strip())
            return g.get("X", 0), g.get("Y", 0), g.get("WIDTH", 1280), g.get("HEIGHT", 900)
        except Exception:
            return 0, 0, 1280, 900


def _linux_window_title(wid):
    try:
        import subprocess
        env = os.environ.copy(); env.setdefault("DISPLAY", ":99")
        r = subprocess.run(
            ["xdotool", "getwindowname", str(wid)],
            capture_output=True, text=True, env=env
        )
        return r.stdout.strip()
    except Exception:
        return ""


# Patch find_browser_linux to return a _LinuxWindow wrapper
def _find_browser_linux_wrapped():
    wid = _find_browser_linux()
    if wid:
        return _LinuxWindow(wid)
    return None

# Override for Linux
if not _IS_WINDOWS:
    _orig_find = find_browser_window
    def find_browser_window():
        return _find_browser_linux_wrapped()


def get_window_title(win):
    try:
        return win.title if win else ""
    except Exception:
        return ""


def get_screen_size():
    return _pag().size()


def focus_window(win):
    """Bring the browser window to the front and give it keyboard focus."""
    try:
        win.activate()
    except Exception:
        pass
    time.sleep(0.5)


# ── Input helpers ────────────────────────────────────────────────────────────

def key(*keys):
    """Press a keyboard shortcut, e.g. key('ctrl','t')."""
    _pag().hotkey(*keys)
    time.sleep(0.05)


def paste_text(text):
    """
    Copy text to clipboard and paste it.
    More reliable than typing character-by-character for passwords
    that contain special characters.
    """
    _clip().copy(text)
    time.sleep(0.15)
    key("ctrl", "v")
    time.sleep(0.1)


def human_type(text, stop_event=None):
    """Type text with random human-like delays and occasional typos."""
    lo, hi = config.get_typing_delays()
    typo_rate = config.get_typo_rate()
    pag = _pag()

    for ch in text:
        if stop_event and stop_event.is_set():
            return
        # Occasional typo
        if random.random() < typo_rate:
            wrong = random.choice("abcdefghijklmnopqrstuvwxyz")
            pag.write(wrong, interval=0)
            time.sleep(random.uniform(0.08, 0.18))
            key("backspace")
            time.sleep(random.uniform(0.05, 0.12))
        # Type the real character
        try:
            pag.write(ch, interval=random.uniform(lo, hi))
        except Exception:
            # pyautogui.write can't handle some unicode — fall back to clipboard
            _clip().copy(ch)
            key("ctrl", "v")


def human_mouse_move(x, y):
    """Move the mouse in a smooth curved arc to (x, y)."""
    pag = _pag()
    duration = random.uniform(0.25, 0.6)
    pag.moveTo(x, y, duration=duration, tween=pag.easeInOutQuad)


def human_click(x, y):
    human_mouse_move(x, y)
    time.sleep(random.uniform(0.06, 0.18))
    _pag().click()
    time.sleep(random.uniform(0.05, 0.12))


# ── Stop / sleep helpers ─────────────────────────────────────────────────────

def check_stop(stop_event):
    return bool(stop_event and stop_event.is_set())


def isleep(seconds, stop_event=None):
    """Sleep in 0.1 s ticks so we can react to stop signals quickly."""
    for _ in range(int(seconds * 10)):
        if check_stop(stop_event):
            return True
        time.sleep(0.1)
    return check_stop(stop_event)


# ── Core login flow ──────────────────────────────────────────────────────────

def login_single(win, email, password,
                 twofa_enabled, twofa_type, totp_secret,
                 log, stop_event):
    """
    Log in to one Google account by controlling an open browser window
    with pyautogui mouse/keyboard. Sessions are saved in the browser's
    own profile — nothing is isolated.
    """
    W, H = get_screen_size()

    # Work out the centre of the browser's content area
    try:
        bx = win.left + win.width  // 2
        by = win.top  + win.height // 2
    except Exception:
        bx, by = W // 2, H // 2

    # ── Bring browser to front ────────────────────────────────────────────
    focus_window(win)

    # ── Open a new tab ────────────────────────────────────────────────────
    key("ctrl", "t")
    if isleep(0.9, stop_event): return "STOPPED"

    # ── Navigate to Google login ──────────────────────────────────────────
    key("ctrl", "l")          # focus address bar
    time.sleep(0.2)
    key("ctrl", "a")          # select any existing URL
    time.sleep(0.1)
    _pag().write("https://accounts.google.com", interval=0.02)
    key("return")
    log("  → Navigating to Google login page...")
    if isleep(3.5, stop_event): return "STOPPED"

    # Dismiss GDPR/cookie overlay if present
    key("escape")
    time.sleep(0.3)

    # ── Enter email ───────────────────────────────────────────────────────
    # Google auto-focuses the email field when the page loads.
    # Click roughly in the centre of the page to be safe.
    human_click(bx, by)
    time.sleep(0.3)

    log("  → Entering email...")
    paste_text(email)         # paste = handles all special chars
    time.sleep(0.2)
    key("return")

    # ── Wait for password page ────────────────────────────────────────────
    log("  → Waiting for password field...")
    if isleep(3.0, stop_event): return "STOPPED"

    # ── Enter password ────────────────────────────────────────────────────
    human_click(bx, by)
    time.sleep(0.3)

    log("  → Entering password...")
    paste_text(password)
    time.sleep(0.2)
    key("return")

    # ── Wait for result ───────────────────────────────────────────────────
    log("  → Submitted — waiting for result...")
    if isleep(4.5, stop_event): return "STOPPED"

    title = get_window_title(win).lower()

    # ── Handle 2FA ────────────────────────────────────────────────────────
    if twofa_enabled and any(kw in title for kw in
                             ("verify", "2-step", "challenge", "sign in")):
        if twofa_type == "Authenticator" and totp_secret:
            code = pyotp.TOTP(totp_secret).now()
            log(f"  → 2FA (TOTP) — entering code {code}...")
            human_click(bx, by)
            time.sleep(0.3)
            pyautogui.write(code, interval=0.1)
            key("return")
            if isleep(4.0, stop_event): return "STOPPED"

        elif twofa_type in ("SMS", "Email", "Google Prompt"):
            log(f"  → 2FA ({twofa_type}) — waiting for manual verification...")
            timeout = config.get_twofa_timeout()
            prev = get_window_title(win).lower()
            for _ in range(timeout):
                if check_stop(stop_event): return "STOPPED"
                time.sleep(1)
                cur = get_window_title(win).lower()
                if "verify" not in cur and "2-step" not in cur \
                        and "challenge" not in cur and cur != prev:
                    break
            else:
                return "2FA_TIMEOUT"

    # ── Detect final state ────────────────────────────────────────────────
    title = get_window_title(win).lower()

    if "wrong" in title or "incorrect" in title:
        return "WRONG_PASSWORD"
    if "disabled" in title or "suspended" in title:
        return "ACCOUNT_DISABLED"
    if "blocked" in title or "captcha" in title or "unusual" in title:
        return "BLOCKED_OR_CAPTCHA"
    if "sign in" in title and "google" in title:
        return "WRONG_PASSWORD"

    return "SUCCESS"


# ── Public entry point ───────────────────────────────────────────────────────

def login_accounts(accounts, log_callback=None, stop_event=None):
    """
    Find the open browser window and log in each selected account
    using mouse & keyboard automation.
    """
    log = log_callback or print

    win = find_browser_window()
    if not win:
        log("✘ No browser window found.")
        log("  Please open Chrome, Firefox, Edge — any browser — then try again.")
        return

    log(f"✔ Found browser: \"{win.title}\"")
    log("  Starting screen automation...")

    total = len(accounts)
    for idx, acc in enumerate(accounts, start=1):
        if check_stop(stop_event):
            log("⏹ Stopped by user.")
            break

        padded = tuple(acc) + (None,) * 12
        (account_id, email, password, twofa_enabled,
         twofa_type, country_code, phone_number,
         totp_secret, *_) = padded

        log("─" * 50)
        log(f"[{idx}/{total}] {email}")
        update_account_status(account_id, "LOGGING_IN")

        # Re-find window each time in case user switched browsers
        win = find_browser_window() or win

        try:
            status = login_single(
                win, email, password,
                bool(twofa_enabled),
                twofa_type or "None",
                totp_secret,
                log, stop_event,
            )
        except Exception:
            log(traceback.format_exc())
            status = "ERROR"

        update_account_status(account_id, status)

        icons = {
            "SUCCESS": "✓", "STOPPED": "⏹",
            "WRONG_PASSWORD": "✗", "ACCOUNT_DISABLED": "✗",
            "BLOCKED_OR_CAPTCHA": "⚠", "2FA_TIMEOUT": "⚠",
            "ERROR": "✗",
        }
        log(f"  {icons.get(status,'?')} [{email}] → {status}")

        if status == "STOPPED":
            break

        if idx < total and not check_stop(stop_event):
            gap_min, gap_max = config.get_account_gap()
            gap = random.uniform(gap_min, gap_max)
            log(f"  Waiting {gap:.1f}s before next account...")
            isleep(gap, stop_event)

    log("─" * 50)
    log("✔ Done.")
