import random
import subprocess
import time
import requests
import os
import pyotp
import datetime
from playwright.sync_api import sync_playwright

from database import update_account_status

DEBUG_PORT = 9222

# Find Chrome path automatically
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
]
CHROME_PATH = None
for path in CHROME_PATHS:
    if os.path.exists(path):
        CHROME_PATH = path
        break
if not CHROME_PATH:
    CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"  # fallback


# ==========================
# INTERRUPTIBLE SLEEP
# ==========================

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
    # Remaining fractional sleep
    rem = seconds - (steps * 0.1)
    if rem > 0:
        time.sleep(rem)
    return check_stop(stop_event)


def human_delay(a=0.5, b=1.8, stop_event=None):
    sec = random.uniform(a, b)
    return interruptible_sleep(sec, stop_event)


# ==========================
# START CHROME DEBUG MODE
# ==========================

def start_chrome(log_callback=None):
    try:
        # Check if Chrome debugger is already running
        try:
            res = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2)
            if res.status_code == 200:
                if log_callback:
                    log_callback("Found existing active Chrome debug session. Reusing it.")
                return True
        except:
            pass

        if log_callback:
            log_callback("Launching your primary Chrome browser with debugging enabled...")

        subprocess.Popen([
            CHROME_PATH,
            f"--remote-debugging-port={DEBUG_PORT}",
            "--start-maximized"
        ])

        # wait for debugger
        connected = False
        for _ in range(8):
            try:
                requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
                connected = True
                break
            except:
                time.sleep(1)

        if not connected:
            if log_callback:
                log_callback("Hanging background Chrome instances detected. Clearing and restarting...")
            
            # Terminate background tasks
                    # os.system("taskkill /f /im chrome.exe >nul 2>os.system("taskkill /f /im chrome.exe >nul 2>&1")1")
            time.sleep(2)

            # Relaunch
            subprocess.Popen([
                CHROME_PATH,
                f"--remote-debugging-port={DEBUG_PORT}",
                "--start-maximized"
            ])

            # Wait again
            for _ in range(10):
                try:
                    requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
                    connected = True
                    break
                except:
                    time.sleep(1)

        if connected:
            if log_callback:
                log_callback("Chrome debugger connected successfully.")
            return True

        if log_callback:
            log_callback("Could not connect to Chrome. Please verify if another program is blocking port 9222.")
        return False

    except Exception as e:
        if log_callback:
            log_callback(f"Chrome startup failed: {e}")
        return False


# ==========================
# HUMAN TYPE
# ==========================

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
    except Exception as e:
        return True


# ==========================
# HUMAN CLICK
# ==========================

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
    except Exception as e:
        return True


# ==========================
# AUTO SKIP
# ==========================

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
            btn = page.locator(f'button:has-text("{text}"), div[role="button"]:has-text("{text}")').first
            if btn.count() > 0 and btn.is_visible():
                if log_callback:
                    log_callback(f"Auto-skipping dialog: '{text}'")
                human_click(page, f'button:has-text("{text}"), div[role="button"]:has-text("{text}")', stop_event)
                human_delay(0.8, 1.5, stop_event)
        except:
            pass


# ==========================
# LOGIN DETECTION
# ==========================

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
    
    # Check if there is an avatar or Google account page indicators
    try:
        if page.locator('a[href*="SignOutOptions"]').count() > 0:
            return True
    except:
        pass
    return False


def check_login_errors(page):
    try:
        # Check for wrong email
        email_err = page.locator('div:has-text("Couldn\'t find your Google Account"), div:has-text("Enter a valid email")')
        for i in range(email_err.count()):
            if email_err.nth(i).is_visible():
                return "WRONG_EMAIL"

        # Check for wrong password
        pass_err = page.locator('span:has-text("Wrong password"), div:has-text("Wrong password")')
        for i in range(pass_err.count()):
            if pass_err.nth(i).is_visible():
                return "WRONG_PASSWORD"

        # Check for captcha (must be a visible, interactive captcha challenge)
        captcha_input = page.locator('input#ca, input[name="ca"]').first
        captcha_image = page.locator('img#captchaImg, img[src*="evaluation"]').first
        re_captcha_anchor = page.locator('iframe[title="reCAPTCHA"][src*="frame"], iframe[src*="api2/anchor"]').first
        
        # Only trigger if the actual captcha inputs or challenge frames are visible
        if (captcha_input.count() > 0 and captcha_input.is_visible()) or \
           (captcha_image.count() > 0 and captcha_image.is_visible()) or \
           (re_captcha_anchor.count() > 0 and re_captcha_anchor.is_visible()):
            return "CAPTCHA_REQUIRED"

        # Check for disabled account
        disabled = page.locator('h1:has-text("Account disabled"), div:has-text("Your account has been disabled")')
        for i in range(disabled.count()):
            if disabled.nth(i).is_visible():
                return "ACCOUNT_DISABLED"

    except Exception:
        pass
    return None


def wait_for_captcha_solve(page, log_callback=None, stop_event=None):
    if log_callback:
        log_callback("Google CAPTCHA detected! Please solve the CAPTCHA manually in the Chrome window. The bot will wait up to 120 seconds and resume automatically...")
    
    # Wait up to 120 seconds (60 * 2s)
    for _ in range(60):
        if check_stop(stop_event):
            return "CANCELLED"
        time.sleep(2)
        
        # Check if captcha elements are still visible on page
        try:
            captcha = page.locator('iframe[src*="recaptcha"], div:has-text("Type the text you hear or see"), iframe[title*="reCAPTCHA"]').first
            captcha_visible = captcha.count() > 0 and captcha.is_visible()
        except:
            captcha_visible = False
            
        if not captcha_visible:
            # Confirm if the error code changed
            err = check_login_errors(page)
            if err != "CAPTCHA_REQUIRED":
                if log_callback:
                    log_callback("CAPTCHA solved successfully! Resuming...")
                return "SOLVED"
                
    return "TIMEOUT"


# ==========================
# SMS HANDLER
# ==========================

def handle_sms(page, country_code, phone_number, log_callback=None, stop_event=None):
    try:
        phone_input = page.locator('input[type="tel"]').first
        if phone_input.count() > 0 and phone_input.is_visible():
            full_number = f"{country_code}{phone_number}"
            if log_callback:
                log_callback(f"Entering phone verification number: {full_number}")
            
            # Clear existing number if any
            phone_input.fill("")
            human_type(page, 'input[type="tel"]', full_number, stop_event)
            if human_delay(0.5, 1.0, stop_event):
                return "CANCELLED"

        send_btn = page.locator('button:has-text("Send"), button:has-text("Next")').first
        if send_btn.count() > 0 and send_btn.is_visible():
            human_click(page, 'button:has-text("Send"), button:has-text("Next")', stop_event)
            if log_callback:
                log_callback("SMS code requested.")
            if human_delay(1.0, 2.0, stop_event):
                return "CANCELLED"

        if log_callback:
            log_callback("Waiting for you to enter SMS code manually in the browser...")

        # Wait up to 120 seconds or until logged in
        for _ in range(40):
            if check_stop(stop_event):
                return "CANCELLED"
            auto_skip(page, log_callback, stop_event)
            if is_logged_in(page):
                return "SUCCESS"
            time.sleep(3)

        return "2FA_TIMEOUT"
    except Exception as e:
        if log_callback:
            log_callback(f"SMS error: {e}")
        return "SMS_ERROR"


# ==========================
# MAIN LOGIN
# ==========================

def login_accounts(accounts, log_callback=None, stop_event=None):
    started = start_chrome(log_callback)
    if not started:
        if log_callback:
            log_callback("Aborted: Chrome debugger not available.")
        return

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
            context = browser.contexts[0]
            page = context.new_page()
        except Exception as e:
            if log_callback:
                log_callback(f"Failed to connect Playwright: {e}")
            return

        for acc in accounts:
            if check_stop(stop_event):
                break

            account_id = acc[0]
            email = acc[1]
            password = acc[2]
            twofa_enabled = acc[3]
            twofa_type = acc[4]
            country_code = acc[5]
            phone_number = acc[6]
            totp_secret = acc[7] if len(acc) > 7 else None

            status = "PENDING"
            try:
                if log_callback:
                    log_callback("=" * 40)
                    log_callback(f"Starting Login Flow: {email}")

                update_account_status(account_id, "LOGGING_IN")
                
                # Navigate to login page
                page.goto("https://accounts.google.com/AddSession", timeout=60000)
                if human_delay(2, 4, stop_event):
                    status = "CANCELLED"
                    break

                auto_skip(page, log_callback, stop_event)

                if is_logged_in(page):
                    if log_callback:
                        log_callback("Session already authenticated.")
                    status = "SUCCESS"
                    update_account_status(account_id, "SUCCESS")
                    continue

                # CHOOSE AN ACCOUNT DETECTION
                # Wait a brief moment in case the page is loading list entries
                for _ in range(3):
                    if page.locator('div:has-text("Use another account"), [data-email]').count() > 0:
                        break
                    time.sleep(1)
                
                use_another = page.locator('div:has-text("Use another account"), div[role="link"]:has-text("Use another account"), [role="button"]:has-text("Use another account")').first
                has_accounts_list = page.locator('[data-email]').count() > 0 or page.locator('div[role="link"]:has-text("@")').count() > 0
                
                if has_accounts_list or (use_another.count() > 0 and use_another.is_visible()):
                    if log_callback:
                        log_callback("Google 'Choose an account' screen detected.")
                    
                    email_found = False
                    for selector_attempt in [
                        f'div[data-email="{email}"]',
                        f'div[role="link"]:has-text("{email}")',
                        f'div:has-text("{email}")',
                        f'[role="button"]:has-text("{email}")'
                    ]:
                        loc = page.locator(selector_attempt).first
                        if loc.count() > 0 and loc.is_visible():
                            # Check bounding box to verify it's a clickable list item
                            box = loc.bounding_box()
                            if box and box["width"] < 700:
                                if log_callback:
                                    log_callback(f"Account entry for {email} found in list. Clicking it...")
                                human_click(page, selector_attempt, stop_event)
                                email_found = True
                                break
                    
                    if not email_found:
                        if log_callback:
                            log_callback(f"Account {email} not in list. Clicking 'Use another account'...")
                        use_another_selector = 'div:has-text("Use another account"), div[role="link"]:has-text("Use another account"), [role="button"]:has-text("Use another account")'
                        human_click(page, use_another_selector, stop_event)
                    
                    if human_delay(2.5, 4.5, stop_event):
                        status = "CANCELLED"
                        break

                # EMAIL STEP
                email_input = page.locator('input[type="email"]').first
                if email_input.count() > 0 and email_input.is_visible():
                    if log_callback:
                        log_callback("Entering email...")
                    email_input.fill("")  # clear first
                    if human_type(page, 'input[type="email"]', email, stop_event):
                        status = "CANCELLED"
                        break
                    
                    if human_delay(0.5, 1.2, stop_event):
                        status = "CANCELLED"
                        break
                    page.keyboard.press("Enter")
                    
                    if human_delay(3, 5, stop_event):
                        status = "CANCELLED"
                        break

                # Check for errors after email
                err = check_login_errors(page)
                if err == "CAPTCHA_REQUIRED":
                    res = wait_for_captcha_solve(page, log_callback, stop_event)
                    if res == "CANCELLED":
                        status = "CANCELLED"
                        break
                    elif res == "TIMEOUT":
                        status = "CAPTCHA_REQUIRED"
                        update_account_status(account_id, "CAPTCHA_REQUIRED")
                        continue
                    else:
                        # Re-verify error after solve
                        err = check_login_errors(page)
                        if err and err != "CAPTCHA_REQUIRED":
                            status = err
                            update_account_status(account_id, err)
                            continue
                elif err:
                    if log_callback:
                        log_callback(f"Error after Email: {err}")
                    status = err
                    update_account_status(account_id, err)
                    continue

                # PASSWORD STEP
                password_input = page.locator('input[type="password"]').first
                # Wait a bit if it's loading
                for _ in range(5):
                    if password_input.count() > 0 and password_input.is_visible():
                        break
                    time.sleep(1)
                    if check_stop(stop_event):
                        break

                if check_stop(stop_event):
                    status = "CANCELLED"
                    break

                # Try to solve captcha if password is not visible first
                if not (password_input.count() > 0 and password_input.is_visible()):
                    err = check_login_errors(page)
                    if err == "CAPTCHA_REQUIRED":
                        res = wait_for_captcha_solve(page, log_callback, stop_event)
                        if res == "SOLVED":
                            # Wait up to 5 seconds for password field to appear after solving
                            for _ in range(5):
                                if password_input.count() > 0 and password_input.is_visible():
                                    break
                                time.sleep(1)
                        elif res == "CANCELLED":
                            status = "CANCELLED"
                            break
                        else:
                            status = "CAPTCHA_REQUIRED"
                            update_account_status(account_id, "CAPTCHA_REQUIRED")
                            continue

                if password_input.count() > 0 and password_input.is_visible():
                    if log_callback:
                        log_callback("Entering password...")
                    password_input.fill("")
                    if human_type(page, 'input[type="password"]', password, stop_event):
                        status = "CANCELLED"
                        break
                    
                    if human_delay(0.5, 1.2, stop_event):
                        status = "CANCELLED"
                        break
                    page.keyboard.press("Enter")
                    
                    if human_delay(4, 6, stop_event):
                        status = "CANCELLED"
                        break
                else:
                    # Password field never appeared, let's see why
                    err = check_login_errors(page)
                    if err == "CAPTCHA_REQUIRED":
                        res = wait_for_captcha_solve(page, log_callback, stop_event)
                        if res == "CANCELLED":
                            status = "CANCELLED"
                            break
                        elif res == "TIMEOUT":
                            status = "CAPTCHA_REQUIRED"
                            update_account_status(account_id, "CAPTCHA_REQUIRED")
                            continue
                    elif err:
                        if log_callback:
                            log_callback(f"Error: {err}")
                        status = err
                        update_account_status(account_id, err)
                        continue
                    else:
                        if log_callback:
                            log_callback("Password field not found. Captcha or manual action might be blocking.")
                        status = "BLOCKED_OR_CAPTCHA"
                        update_account_status(account_id, "BLOCKED_OR_CAPTCHA")
                        continue

                # Check for errors after password
                err = check_login_errors(page)
                if err == "CAPTCHA_REQUIRED":
                    res = wait_for_captcha_solve(page, log_callback, stop_event)
                    if res == "CANCELLED":
                        status = "CANCELLED"
                        break
                    elif res == "TIMEOUT":
                        status = "CAPTCHA_REQUIRED"
                        update_account_status(account_id, "CAPTCHA_REQUIRED")
                        continue
                elif err:
                    if log_callback:
                        log_callback(f"Error after Password: {err}")
                    status = err
                    update_account_status(account_id, err)
                    continue

                # 2FA STEP
                auto_skip(page, log_callback, stop_event)

                if is_logged_in(page):
                    status = "SUCCESS"
                elif twofa_enabled:
                    # Let's inspect the page for 2FA boxes
                    if twofa_type == "SMS":
                        status = handle_sms(page, country_code, phone_number, log_callback, stop_event)
                    elif twofa_type == "Authenticator" and totp_secret:
                        # Attempt automatic TOTP input
                        totp_input = page.locator('input#totpPin, input[type="tel"], input[autocomplete="one-time-code"]').first
                        # wait for totp input
                        for _ in range(5):
                            if totp_input.count() > 0 and totp_input.is_visible():
                                break
                            time.sleep(1)
                            if check_stop(stop_event):
                                break

                        if totp_input.count() > 0 and totp_input.is_visible():
                            try:
                                secret_clean = totp_secret.replace(" ", "").upper()
                                totp = pyotp.TOTP(secret_clean)
                                code = totp.now()
                                if log_callback:
                                    log_callback(f"Generating and typing Authenticator (TOTP) code: {code}")
                                human_type(page, totp_input, code, stop_event)
                                if human_delay(0.5, 1.2, stop_event):
                                    status = "CANCELLED"
                                    break
                                page.keyboard.press("Enter")
                                if human_delay(4, 7, stop_event):
                                    status = "CANCELLED"
                                    break
                            except Exception as ex:
                                if log_callback:
                                    log_callback(f"TOTP generation failed: {ex}")
                                status = "TOTP_GEN_FAILED"

                        if is_logged_in(page):
                            status = "SUCCESS"
                        else:
                            # Fallback to manual for Authenticator if it didn't complete
                            if log_callback:
                                log_callback("TOTP entered but not logged in. Waiting for manual 2FA completion...")
                            for _ in range(30):
                                if check_stop(stop_event):
                                    status = "CANCELLED"
                                    break
                                auto_skip(page, log_callback, stop_event)
                                if is_logged_in(page):
                                    status = "SUCCESS"
                                    break
                                time.sleep(3)
                            if status != "SUCCESS" and status != "CANCELLED":
                                status = "2FA_TIMEOUT"
                    else:
                        # Other 2FA / Manual
                        if log_callback:
                            log_callback(f"2FA type '{twofa_type}' enabled. Waiting for manual authentication in Chrome...")
                        for _ in range(40):
                            if check_stop(stop_event):
                                status = "CANCELLED"
                                break
                            auto_skip(page, log_callback, stop_event)
                            if is_logged_in(page):
                                status = "SUCCESS"
                                break
                            time.sleep(3)
                        if status != "SUCCESS" and status != "CANCELLED":
                            status = "2FA_TIMEOUT"
                else:
                    # 2FA not enabled but not logged in either
                    # Let's wait a few seconds in case of slow redirect
                    for _ in range(3):
                        if is_logged_in(page):
                            status = "SUCCESS"
                            break
                        time.sleep(2)
                    
                    if status != "SUCCESS":
                        err = check_login_errors(page)
                        if err:
                            status = err
                        else:
                            status = "UNKNOWN_STATE"

                # Final Skip check
                if status == "SUCCESS":
                    auto_skip(page, log_callback, stop_event)
                    if log_callback:
                        log_callback(f"SUCCESS: Successfully logged in to {email}")
                else:
                    if log_callback:
                        log_callback(f"LOGIN FAILED: {email} | Status: {status}")

                update_account_status(account_id, status)
                human_delay(3, 5, stop_event)

            except Exception as e:
                status = "ERROR"
                update_account_status(account_id, "ERROR")
                if log_callback:
                    log_callback(f"Exception during login for {email}: {e}")

            if status == "CANCELLED":
                break

        if log_callback:
            log_callback("=" * 40)
            if check_stop(stop_event):
                log_callback("Process terminated by user.")
            else:
                log_callback("All selected accounts processed.")
        
        try:
            page.close()
        except:
            pass