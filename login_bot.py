import random
import time
import math
import traceback
import pyotp
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from database import update_account_status
import config


# ============================================================
# LOW-LEVEL STOP / SLEEP HELPERS
# ============================================================

def check_stop(stop_event):
    return bool(stop_event and stop_event.is_set())


def interruptible_sleep(seconds, stop_event=None):
    steps = int(seconds * 10)
    for _ in range(steps):
        if check_stop(stop_event):
            return True
        time.sleep(0.1)
    rem = seconds - steps * 0.1
    if rem > 0:
        time.sleep(rem)
    return check_stop(stop_event)


def human_delay(a=0.5, b=1.8, stop_event=None):
    return interruptible_sleep(random.uniform(a, b), stop_event)


# ============================================================
# HUMAN MOUSE MOVEMENT
# ============================================================

def _bezier_curve(p0, p1, p2, p3, steps=30):
    """Return a list of (x, y) points along a cubic Bezier curve."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt**3 * p0[0] + 3 * mt**2 * t * p1[0]
             + 3 * mt * t**2 * p2[0] + t**3 * p3[0])
        y = (mt**3 * p0[1] + 3 * mt**2 * t * p1[1]
             + 3 * mt * t**2 * p2[1] + t**3 * p3[1])
        points.append((x, y))
    return points


def human_mouse_move(page, x_end, y_end, stop_event=None):
    """
    Move the mouse from its current position to (x_end, y_end) along
    a randomised cubic Bezier curve, simulating realistic hand movement.
    """
    try:
        # Get current mouse position from JS; default to a central spot
        pos = page.evaluate("() => ({ x: window._mouseX || 640, y: window._mouseY || 400 })")
        x0, y0 = pos.get("x", 640), pos.get("y", 400)
    except Exception:
        x0, y0 = 640, 400

    # Random control points that produce a natural arc
    cp1 = (x0 + random.uniform(-150, 150), y0 + random.uniform(-150, 150))
    cp2 = (x_end + random.uniform(-150, 150), y_end + random.uniform(-150, 150))

    dist = math.hypot(x_end - x0, y_end - y0)
    steps = max(15, min(80, int(dist / 8)))
    points = _bezier_curve((x0, y0), cp1, cp2, (x_end, y_end), steps)

    for px, py in points:
        if check_stop(stop_event):
            return True
        page.mouse.move(px, py)
        time.sleep(random.uniform(0.004, 0.018))

    # Track position for next call
    try:
        page.evaluate(f"() => {{ window._mouseX = {x_end}; window._mouseY = {y_end}; }}")
    except Exception:
        pass
    return False


def human_mouse_wander(page, stop_event=None):
    """
    Randomly move the mouse to a natural 'idle' position while waiting.
    Simulates a human glancing around the screen.
    """
    try:
        vp = page.viewport_size or {"width": 1280, "height": 800}
        x = random.randint(100, vp["width"] - 100)
        y = random.randint(100, vp["height"] - 100)
        human_mouse_move(page, x, y, stop_event)
    except Exception:
        pass


# ============================================================
# HUMAN CLICK
# ============================================================

def human_click(page, selector, stop_event=None, timeout=8000):
    """
    Move to the element's bounding box with a Bezier curve then click
    at a random position within it, as a human would.
    """
    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=timeout)
        box = el.bounding_box()
        if not box:
            return True

        # Random landing point inside the element (avoid the very edges)
        pad_x = max(4, int(box["width"] * 0.1))
        pad_y = max(4, int(box["height"] * 0.1))
        x = box["x"] + random.randint(pad_x, max(pad_x + 1, int(box["width"]) - pad_x))
        y = box["y"] + random.randint(pad_y, max(pad_y + 1, int(box["height"]) - pad_y))

        if human_mouse_move(page, x, y, stop_event):
            return True

        # Brief hover pause before clicking
        time.sleep(random.uniform(0.06, 0.22))
        page.mouse.click(x, y)
        return False
    except Exception:
        return True


# ============================================================
# HUMAN TYPING  (with occasional typo + backspace)
# ============================================================

# Characters that are "adjacent" on a QWERTY keyboard, for typo simulation
_ADJACENT = {
    'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr', 'f': 'dg',
    'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk', 'k': 'jl', 'l': 'k',
    'm': 'n', 'n': 'mb', 'o': 'ip', 'p': 'o', 'q': 'wa', 'r': 'et',
    's': 'ad', 't': 'ry', 'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc',
    'y': 'tu', 'z': 'x',
}
def human_type(page, selector, text, stop_event=None, clear_first=True):
    """
    Click on the field then type each character with randomised inter-key
    delays. Occasionally introduces a typo and corrects it with Backspace.
    Delay range and typo rate are read live from config.
    """
    # Read settings fresh each call so changes take effect immediately
    key_min, key_max = config.get_typing_delays()
    typo_rate = config.get_typo_rate()

    try:
        el = page.locator(selector).first
        el.wait_for(state="visible", timeout=8000)

        if human_click(page, selector, stop_event):
            return True

        if clear_first:
            page.keyboard.press("Control+a")
            time.sleep(0.05)
            page.keyboard.press("Delete")
            time.sleep(0.1)

        human_delay(0.15, 0.4, stop_event)

        for char in text:
            if check_stop(stop_event):
                return True

            # Occasional typo
            if char.isalpha() and random.random() < typo_rate:
                candidates = _ADJACENT.get(char.lower(), "")
                if candidates:
                    wrong = random.choice(candidates)
                    if char.isupper():
                        wrong = wrong.upper()
                    page.keyboard.type(wrong)
                    time.sleep(random.uniform(0.08, 0.18))
                    page.keyboard.press("Backspace")
                    time.sleep(random.uniform(0.05, key_max))

            page.keyboard.type(char)
            # Natural inter-key delay (from config)
            time.sleep(random.uniform(key_min, key_max))

            # Occasional micro-pause (thinking pause)
            if random.random() < 0.04:
                time.sleep(random.uniform(0.2, 0.6))

        return False
    except Exception:
        return True


# ============================================================
# PAGE WAIT HELPERS
# ============================================================

def wait_for_navigation(page, stop_event=None, timeout=15):
    """Wait for the page URL or DOM to settle after clicking."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
    except Exception:
        pass
    if interruptible_sleep(random.uniform(0.6, 1.2), stop_event):
        return True
    return False


def wait_for_selector_or_url(page, selectors, url_fragments,
                              timeout=20, stop_event=None):
    """
    Poll until one of the given CSS selectors appears OR the URL contains
    one of the given fragments.  Returns ('selector', matched_val) or
    ('url', matched_fragment) or ('timeout', None).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check_stop(stop_event):
            return ("stopped", None)
        try:
            for url_frag in url_fragments:
                if url_frag in page.url:
                    return ("url", url_frag)
            for sel in selectors:
                el = page.locator(sel).first
                if el.count() > 0 and el.is_visible():
                    return ("selector", sel)
        except Exception:
            pass
        time.sleep(0.4)
    return ("timeout", None)


# ============================================================
# POST-LOGIN DIALOG AUTO-SKIPPER
# ============================================================

_SKIP_TEXTS = [
    "Skip",
    "Not now",
    "Remind me later",
    "Confirm later",
    "Keep current",
    "Done",
    "Continue",
    "No thanks",
    "Dismiss",
    "Got it",
    "Maybe later",
]

_SKIP_URLS = [
    "myaccount.google.com",
    "mail.google.com",
    "accounts.google.com/b/",
]


def auto_skip_dialogs(page, log_callback=None, stop_event=None, rounds=5):
    """
    Repeatedly scan for common post-login interstitial dialogs and dismiss
    them.  Runs up to `rounds` passes to catch chained dialogs.
    """
    for _ in range(rounds):
        if check_stop(stop_event):
            return
        skipped_any = False
        for text in _SKIP_TEXTS:
            if check_stop(stop_event):
                return
            try:
                sel = (f'button:has-text("{text}"), '
                       f'div[role="button"]:has-text("{text}"), '
                       f'a:has-text("{text}")')
                btn = page.locator(sel).first
                if btn.count() > 0 and btn.is_visible():
                    if log_callback:
                        log_callback(f"  ↪ Auto-dismissed dialog: '{text}'")
                    human_click(page, sel, stop_event)
                    human_delay(0.8, 1.6, stop_event)
                    skipped_any = True
            except Exception:
                pass
        if not skipped_any:
            break
        human_delay(0.5, 1.0, stop_event)


# ============================================================
# LOGIN STATE DETECTION
# ============================================================

def is_logged_in(page):
    url = page.url.lower()
    success_fragments = [
        "mail.google.com",
        "myaccount.google.com",
        "workspace.google.com",
        "contacts.google.com",
        "drive.google.com",
        "accounts.google.com/b/",         # multi-account selector
        "google.com/u/",                   # signed-in redirect
    ]
    for frag in success_fragments:
        if frag in url:
            return True
    try:
        if page.locator('a[href*="SignOutOptions"]').count() > 0:
            return True
        # Google's account avatar in the top bar
        if page.locator('a[aria-label*="Google Account"]').count() > 0:
            return True
    except Exception:
        pass
    return False


def detect_login_error(page):
    """
    Return an error string if a recognisable failure state is on screen,
    otherwise return None.
    """
    try:
        # Wrong email
        for txt in ["Couldn't find your Google Account",
                    "Enter a valid email or phone number"]:
            if page.locator(f'text="{txt}"').count() > 0:
                return "WRONG_EMAIL"

        # Wrong password
        for txt in ["Wrong password", "Incorrect password"]:
            if page.locator(f'text="{txt}"').count() > 0:
                return "WRONG_PASSWORD"

        # Account disabled
        for txt in ["Account disabled", "Your account has been disabled"]:
            if page.locator(f'text="{txt}"').count() > 0:
                return "ACCOUNT_DISABLED"

        # Captcha / unusual activity
        captcha_selectors = [
            'input#ca', 'input[name="ca"]',
            'img#captchaImg',
            'iframe[src*="api2/anchor"]',
            'iframe[title*="reCAPTCHA"]',
        ]
        for sel in captcha_selectors:
            el = page.locator(sel).first
            if el.count() > 0 and el.is_visible():
                return "BLOCKED_OR_CAPTCHA"

        for txt in ["unusual activity", "suspicious activity",
                    "verify it's you", "Verify your identity"]:
            if page.locator(f'text="{txt}"').count() > 0:
                return "BLOCKED_OR_CAPTCHA"

    except Exception:
        pass
    return None


# ============================================================
# 2FA HANDLERS
# ============================================================

def handle_totp_2fa(page, totp_secret, log_callback=None, stop_event=None):
    """Auto-generate and enter the TOTP code for Authenticator 2FA."""
    if log_callback:
        log_callback("  ✦ Generating TOTP code...")
    try:
        code = pyotp.TOTP(totp_secret).now()
        if log_callback:
            log_callback(f"  ✦ TOTP code generated (6 digits).")

        # Find the OTP input field
        otp_sel = ('input[type="tel"], input[type="number"], '
                   'input[autocomplete="one-time-code"], '
                   'input[inputmode="numeric"]')
        kind, _ = wait_for_selector_or_url(
            page, [otp_sel], [], timeout=10, stop_event=stop_event
        )
        if kind == "selector":
            if human_type(page, otp_sel, code, stop_event):
                return False
            human_delay(0.5, 1.0, stop_event)
            # Click Next / Verify
            for btn_sel in ['#passwordNext', 'button[type="submit"]',
                            'div[role="button"]:has-text("Next")',
                            'button:has-text("Next")',
                            'button:has-text("Verify")']:
                try:
                    if page.locator(btn_sel).count() > 0:
                        human_click(page, btn_sel, stop_event)
                        break
                except Exception:
                    pass
            return True
        return False
    except Exception as e:
        if log_callback:
            log_callback(f"  ✦ TOTP error: {e}")
        return False


def handle_manual_2fa(page, method, log_callback=None, stop_event=None):
    """
    For SMS / Email / Google Prompt 2FA: wait for the user to complete
    verification in the browser window.  Polls for config.get_twofa_timeout() secs.
    """
    timeout_secs = config.get_twofa_timeout()
    if log_callback:
        log_callback(
            f"  ⚠ {method} 2FA detected — please complete verification "
            f"in the browser window within {timeout_secs}s..."
        )

    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        if check_stop(stop_event):
            return False
        if is_logged_in(page):
            return True
        # Wander mouse occasionally to look human while waiting
        if random.random() < 0.08:
            human_mouse_wander(page, stop_event)
        time.sleep(1.0)

    if log_callback:
        log_callback(f"  ✦ 2FA timeout ({timeout_secs}s) — skipping account.")
    return False


def handle_2fa_step(page, twofa_type, totp_secret,
                    log_callback=None, stop_event=None):
    """
    Detect and route to the right 2FA handler.
    Returns True if 2FA was handled (or not needed), False on failure/timeout.
    """
    if log_callback:
        log_callback(f"  ✦ Handling 2FA method: {twofa_type}")

    if twofa_type == "Authenticator" and totp_secret:
        return handle_totp_2fa(page, totp_secret, log_callback, stop_event)

    # SMS / Email / Google Prompt — need user to act in the browser
    return handle_manual_2fa(page, twofa_type, log_callback, stop_event)


# ============================================================
# MAIN LOGIN FLOW FOR A SINGLE ACCOUNT
# ============================================================

def login_single_account(page, email, password, twofa_enabled,
                         twofa_type, totp_secret,
                         log_callback=None, stop_event=None):
    """
    Execute the full Google login sequence for one account.
    Returns a status string: SUCCESS, WRONG_EMAIL, WRONG_PASSWORD,
    ACCOUNT_DISABLED, BLOCKED_OR_CAPTCHA, 2FA_TIMEOUT, or ERROR.
    """
    log = log_callback or (lambda _: None)

    # ── Step 1: Navigate to the Add-Account page ──────────────────────
    log("  → Navigating to Google sign-in page...")
    try:
        page.goto("https://accounts.google.com/AddSession",
                  wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"  ✗ Navigation failed: {e}")
        return "ERROR"

    human_delay(1.0, 2.2, stop_event)
    if check_stop(stop_event):
        return "STOPPED"

    # Idle wander while page settles
    human_mouse_wander(page, stop_event)
    human_delay(0.4, 1.0, stop_event)

    # ── Step 2: Enter email ───────────────────────────────────────────
    log("  → Entering email address...")
    email_sel = 'input[type="email"], input[name="identifier"]'
    kind, _ = wait_for_selector_or_url(
        page, [email_sel], [], timeout=15, stop_event=stop_event
    )
    if kind != "selector":
        log("  ✗ Could not find email input field.")
        return "ERROR"

    if human_type(page, email_sel, email, stop_event):
        return "STOPPED"

    # Simulate reading over what was typed
    human_delay(0.4, 0.9, stop_event)
    human_mouse_wander(page, stop_event)
    human_delay(0.3, 0.7, stop_event)

    # Click "Next"
    log("  → Clicking Next after email...")
    next_sel = '#identifierNext, button:has-text("Next"), div[role="button"]:has-text("Next")'
    if human_click(page, next_sel, stop_event):
        return "STOPPED"

    wait_for_navigation(page, stop_event)

    # Check for email error
    err = detect_login_error(page)
    if err:
        log(f"  ✗ Error detected: {err}")
        return err

    # ── Step 3: Enter password ────────────────────────────────────────
    log("  → Waiting for password field...")
    pass_sel = 'input[type="password"], input[name="Passwd"]'
    kind, _ = wait_for_selector_or_url(
        page, [pass_sel], [], timeout=15, stop_event=stop_event
    )
    if kind != "selector":
        # Maybe already on a 2FA page or logged in
        if is_logged_in(page):
            log("  ✓ Already signed in (no password needed).")
            auto_skip_dialogs(page, log_callback, stop_event)
            return "SUCCESS"
        log("  ✗ Password field not found.")
        return "ERROR"

    # Brief human hesitation before typing password
    human_delay(0.6, 1.4, stop_event)
    human_mouse_wander(page, stop_event)
    human_delay(0.3, 0.8, stop_event)

    log("  → Entering password...")
    if human_type(page, pass_sel, password, stop_event):
        return "STOPPED"

    human_delay(0.5, 1.1, stop_event)
    human_mouse_wander(page, stop_event)
    human_delay(0.2, 0.5, stop_event)

    # Click "Next"
    log("  → Clicking Next after password...")
    pw_next_sel = ('#passwordNext, button:has-text("Next"), '
                   'div[role="button"]:has-text("Next")')
    if human_click(page, pw_next_sel, stop_event):
        return "STOPPED"

    wait_for_navigation(page, stop_event)

    # Check for password error
    err = detect_login_error(page)
    if err:
        log(f"  ✗ Error detected: {err}")
        return err

    # ── Step 4: Handle 2FA (if enabled) ──────────────────────────────
    if twofa_enabled and twofa_type and twofa_type != "None":
        log(f"  → 2FA step required ({twofa_type})...")

        # Small wait for 2FA page to load
        human_delay(1.5, 3.0, stop_event)

        if not is_logged_in(page):
            ok = handle_2fa_step(
                page, twofa_type, totp_secret, log_callback, stop_event
            )
            if not ok:
                return "2FA_TIMEOUT"
            wait_for_navigation(page, stop_event)

    # ── Step 5: Wait for successful login ────────────────────────────
    log("  → Waiting for login to complete...")
    deadline = time.time() + 25
    while time.time() < deadline:
        if check_stop(stop_event):
            return "STOPPED"
        if is_logged_in(page):
            break
        err = detect_login_error(page)
        if err:
            log(f"  ✗ Post-login error: {err}")
            return err
        # Drift mouse naturally while waiting
        if random.random() < 0.15:
            human_mouse_wander(page, stop_event)
        time.sleep(0.8)
    else:
        # Final check
        if not is_logged_in(page):
            log("  ✗ Login timed out.")
            return "ERROR"

    # ── Step 6: Dismiss post-login dialogs ───────────────────────────
    log("  → Signed in! Dismissing any post-login dialogs...")
    human_delay(1.0, 2.5, stop_event)
    auto_skip_dialogs(page, log_callback, stop_event)

    return "SUCCESS"


# ============================================================
# MAIN ENTRY POINT (called by the GUI)
# ============================================================

def login_accounts(accounts, log_callback=None, stop_event=None):
    """
    Connect to the user's running Chrome via CDP and sequentially log in
    each of the provided accounts in a new tab.
    """
    log = log_callback or (lambda _: None)

    with sync_playwright() as p:
        # ── Connect to existing Chrome instance ───────────────────────
        try:
            cdp_endpoint = config.get_cdp_endpoint()
            browser = p.chromium.connect_over_cdp(cdp_endpoint)
            context = browser.contexts[0]
            log("✔ Connected to your running Chrome browser.")
        except Exception:
            cdp_port = config.load().get("cdp_port", 9222)
            log("✘ CRITICAL: Could not connect to Chrome.")
            log(f"  Chrome must be running with:  --remote-debugging-port={cdp_port}")
            log("")
            log("  How to set this up:")
            log("  • Windows: Right-click the Chrome shortcut → Properties")
            log("    → append  --remote-debugging-port=9222  to the Target field.")
            log("  • Mac/Linux: launch Chrome from terminal:")
            log('    google-chrome --remote-debugging-port=9222')
            log("")
            log("  Then close all existing Chrome windows and relaunch with that flag.")
            log("─" * 50)
            log(traceback.format_exc())
            return

        # ── Open a single automation tab (reused across accounts) ─────
        page = context.new_page()
        log("✔ Opened a new automation tab in your browser.")

        # ── Process each account sequentially ─────────────────────────
        total = len(accounts)
        for idx, acc in enumerate(accounts, start=1):
            if check_stop(stop_event):
                log("⏹ Automation stopped by user.")
                break

            # Unpack DB row (pad with Nones so we never get IndexError)
            padded = tuple(acc) + (None,) * 12
            (account_id, email, password, twofa_enabled,
             twofa_type, country_code, phone_number,
             totp_secret, *_) = padded

            log("─" * 50)
            log(f"[{idx}/{total}] Starting login for: {email}")

            update_account_status(account_id, "LOGGING_IN")

            try:
                status = login_single_account(
                    page=page,
                    email=email,
                    password=password,
                    twofa_enabled=bool(twofa_enabled),
                    twofa_type=twofa_type or "None",
                    totp_secret=totp_secret,
                    log_callback=log_callback,
                    stop_event=stop_event,
                )
            except Exception:
                log(f"  ✗ Unexpected exception:")
                log(traceback.format_exc())
                status = "ERROR"

            update_account_status(account_id, status)

            if status == "SUCCESS":
                log(f"  ✓ [{email}] → SUCCESS")
            elif status == "STOPPED":
                log(f"  ⏹ [{email}] → Stopped mid-login.")
                break
            else:
                log(f"  ✗ [{email}] → {status}")

            # Gap between accounts so it doesn't look like a bot
            if idx < total and not check_stop(stop_event):
                gap_min, gap_max = config.get_account_gap()
                gap = random.uniform(gap_min, gap_max)
                log(f"  Waiting {gap:.1f}s before next account...")
                interruptible_sleep(gap, stop_event)

        # ── Clean up ──────────────────────────────────────────────────
        log("─" * 50)
        log("✔ All selected accounts processed.")
        try:
            page.close()
            log("✔ Automation tab closed.")
        except Exception as e:
            log(f"  Note: Could not close the tab automatically ({e})")
