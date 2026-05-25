import random
import time
import traceback
from playwright.sync_api import sync_playwright
from database import update_account_status

# ==========================#
# CONNECTION CONFIG
# ==========================#
# This script will connect to an already-running Chrome instance.
# Ensure you have launched Chrome with the command-line flag:
# --remote-debugging-port=9222
CDP_ENDPOINT = "http://localhost:9222"


def check_stop(stop_event):
    if stop_event and stop_event.is_set():
        return True
    return False

def interruptible_sleep(seconds, stop_event=None):
    steps = int(seconds * 10)
    for _ in range(steps):
        if check_stop(stop_event):
            return True
        time.sleep(0.1)
    rem = seconds - (steps * 0.1)
    if rem > 0:
        time.sleep(rem)
    return check_stop(stop_event)

def human_delay(a=0.5, b=1.8, stop_event=None):
    sec = random.uniform(a, b)
    return interruptible_sleep(sec, stop_event)

def human_type(page, selector, text, stop_event=None):
    try:
        page.click(selector)
        if human_delay(0.2, 0.5, stop_event):
            return True
        for char in text:
            if check_stop(stop_event):
                return True
            page.keyboard.type(char)
            time.sleep(random.uniform(0.04, 0.12))
        return False
    except Exception:
        return True

def human_click(page, selector, stop_event=None):
    try:
        element = page.locator(selector).first
        box = element.bounding_box()
        if not box:
            return True

        x = box["x"] + random.randint(5, max(6, int(box["width"]) - 5))
        y = box["y"] + random.randint(5, max(6, int(box["height"]) - 5))

        page.mouse.move(x, y, steps=random.randint(10, 25))
        if human_delay(0.1, 0.3, stop_event):
            return True
        page.mouse.click(x, y)
        return False
    except Exception:
        return True


def auto_skip(page, log_callback=None, stop_event=None):
    buttons = [
        "Skip",
        "Not now",
        "Remind me later",
        "Confirm later",
        "Keep current",
        "Done"
    ]
    for text in buttons:
        if check_stop(stop_event):
            return
        try:
            selector = f'button:has-text("{text}"), div[role="button"]:has-text("{text}")'
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                if log_callback:
                    log_callback(f"Auto-skipping dialog: '{text}'")
                human_click(page, selector, stop_event)
                human_delay(0.8, 1.5, stop_event)
        except Exception:
            pass


def is_logged_in(page):
    url = page.url.lower()
    success_urls = [
        "mail.google.com",
        "myaccount.google.com",
        "workspace.google.com",
        "contacts.google.com",
        "drive.google.com"
    ]
    for item in success_urls:
        if item in url:
            return True

    try:
        if page.locator('a[href*="SignOutOptions"]').count() > 0:
            return True
    except Exception:
        pass
    return False

def check_login_errors(page):
    try:
        email_err = page.locator(
            'div:has-text("Couldn\'t find your Google Account"), div:has-text("Enter a valid email")'
        )
        for i in range(email_err.count()):
            if email_err.nth(i).is_visible():
                return "WRONG_EMAIL"

        pass_err = page.locator(
            'span:has-text("Wrong password"), div:has-text("Wrong password")'
        )
        for i in range(pass_err.count()):
            if pass_err.nth(i).is_visible():
                return "WRONG_PASSWORD"

        captcha_input = page.locator('input#ca, input[name="ca"]').first
        captcha_image = page.locator('img#captchaImg, img[src*="evaluation"]').first
        re_captcha_anchor = page.locator(
            'iframe[title="reCAPTCHA"][src*="frame"], iframe[src*="api2/anchor"]'
        ).first

        if (captcha_input.count() > 0 and captcha_input.is_visible()) or \
           (captcha_image.count() > 0 and captcha_image.is_visible()) or \
           (re_captcha_anchor.count() > 0 and re_captcha_anchor.is_visible()):
            return "CAPTCHA_REQUIRED"

        disabled = page.locator(
            'h1:has-text("Account disabled"), div:has-text("Your account has been disabled")'
        )
        for i in range(disabled.count()):
            if disabled.nth(i).is_visible():
                return "ACCOUNT_DISABLED"

    except Exception:
        pass
    return None

# ==========================#
# MAIN LOGIN
# ==========================#

def login_accounts(accounts, log_callback=None, stop_event=None):
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
            context = browser.contexts[0]
            page = context.new_page()
            if log_callback:
                log_callback("Successfully connected to the running browser and opened a new tab.")

        except Exception as e:
            if log_callback:
                log_callback("CRITICAL: Could not connect to the browser.")
                log_callback(
                    "Please ensure Google Chrome is running and was launched with the "
                    "'--remote-debugging-port=9222' flag."
                )
                log_callback(
                    "Right-click your Chrome shortcut > Properties > Target > "
                    "add ' --remote-debugging-port=9222' to the end."
                )
                log_callback("================= DETAILED ERROR TRACEBACK ==================")
                log_callback(traceback.format_exc())
                log_callback("=============================================================")
            return

        for acc in accounts:
            if check_stop(stop_event):
                break
            account_id, email, password, twofa_enabled, twofa_type, country_code, phone_number, totp_secret, *_ = acc + (None,) * 9

            try:
                if log_callback:
                    log_callback("=" * 40)
                    log_callback(f"Starting Login Flow: {email}")

                update_account_status(account_id, "LOGGING_IN")

                page.goto("https://accounts.google.com/AddSession", timeout=60000)

            except Exception as e:
                if log_callback:
                    log_callback(f"Error processing account {email}: {e}")

        if log_callback:
            log_callback("=" * 40)
            log_callback("All selected accounts processed.")

        try:
            page.close()
            if log_callback:
                log_callback("Automation tab closed.")
        except Exception as e:
            if log_callback:
                log_callback(
                    f"Note: Could not close the page, you may need to close the tab manually. Error: {e}"
                )
