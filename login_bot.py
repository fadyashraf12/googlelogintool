import random
import subprocess
import time
import requests
import os
import pyotp
import datetime
import traceback
from playwright.sync_api import sync_playwright

from database import update_account_status

# ==========================#
# INTERRUPTIBLE SLEEP
# ==========================#

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

# ==========================#
# HUMAN TYPE
# ==========================#

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

# ==========================#
# HUMAN CLICK
# ==========================#

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

# ==========================#
# AUTO SKIP
# ==========================#

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
            btn = page.locator(f'''button:has-text("{text}"), div[role="button"]:has-text("{text}")''').first
            if btn.count() > 0 and btn.is_visible():
                if log_callback:
                    log_callback(f"Auto-skipping dialog: '{text}'")
                human_click(page, f'''button:has-text("{text}"), div[role="button"]:has-text("{text}")''', stop_event)
                human_delay(0.8, 1.5, stop_event)
        except:
            pass

# ==========================#
# LOGIN DETECTION
# ==========================#

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
        if page.locator('''a[href*="SignOutOptions"]''').count() > 0:
            return True
    except:
        pass
    return False

def check_login_errors(page):
    try:
        email_err = page.locator('''div:has-text("Couldn\'t find your Google Account"), div:has-text("Enter a valid email")''')
        for i in range(email_err.count()):
            if email_err.nth(i).is_visible():
                return "WRONG_EMAIL"

        pass_err = page.locator('''span:has-text("Wrong password"), div:has-text("Wrong password")''')
        for i in range(pass_err.count()):
            if pass_err.nth(i).is_visible():
                return "WRONG_PASSWORD"

        captcha_input = page.locator('''input#ca, input[name="ca"]''').first
        captcha_image = page.locator('''img#captchaImg, img[src*="evaluation"]''').first
        re_captcha_anchor = page.locator('''iframe[title="reCAPTCHA"][src*="frame"], iframe[src*="api2/anchor"]''').first
        
        if (captcha_input.count() > 0 and captcha_input.is_visible()) or \
           (captcha_image.count() > 0 and captcha_image.is_visible()) or \
           (re_captcha_anchor.count() > 0 and re_captcha_anchor.is_visible()):
            return "CAPTCHA_REQUIRED"

        disabled = page.locator('''h1:has-text("Account disabled"), div:has-text("Your account has been disabled")''')
        for i in range(disabled.count()):
            if disabled.nth(i).is_visible():
                return "ACCOUNT_DISABLED"

    except Exception:
        pass
    return None

def wait_for_captcha_solve(page, log_callback=None, stop_event=None):
    if log_callback:
        log_callback("Google CAPTCHA detected! Please solve it manually. The bot will wait up to 120 seconds.")
    
    for _ in range(60):
        if check_stop(stop_event):
            return "CANCELLED"
        time.sleep(2)
        
        try:
            captcha = page.locator('''iframe[src*="recaptcha"], div:has-text("Type the text you hear or see"), iframe[title*="reCAPTCHA"]''').first
            captcha_visible = captcha.count() > 0 and captcha.is_visible()
        except:
            captcha_visible = False
            
        if not captcha_visible:
            err = check_login_errors(page)
            if err != "CAPTCHA_REQUIRED":
                if log_callback:
                    log_callback("CAPTCHA solved successfully! Resuming...")
                return "SOLVED"
                
    return "TIMEOUT"

# ==========================#
# SMS HANDLER
# ==========================#

def handle_sms(page, country_code, phone_number, log_callback=None, stop_event=None):
    try:
        phone_input = page.locator('''input[type="tel"]''').first
        if phone_input.count() > 0 and phone_input.is_visible():
            full_number = f"{country_code}{phone_number}"
            if log_callback:
                log_callback(f"Entering phone verification number: {full_number}")
            
            phone_input.fill("")
            human_type(page, '''input[type="tel"]''', full_number, stop_event)
            if human_delay(0.5, 1.0, stop_event):
                return "CANCELLED"

        send_btn = page.locator('''button:has-text("Send"), button:has-text("Next")''').first
        if send_btn.count() > 0 and send_btn.is_visible():
            human_click(page, '''button:has-text("Send"), button:has-text("Next")''', stop_event)
            if log_callback:
                log_callback("SMS code requested.")
            if human_delay(1.0, 2.0, stop_event):
                return "CANCELLED"

        if log_callback:
            log_callback("Waiting for you to enter SMS code manually in the browser...")

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

# ==========================#
# MAIN LOGIN
# ==========================#

def login_accounts(accounts, log_callback=None, stop_event=None):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
        except Exception as e:
            if log_callback:
                log_callback("CRITICAL: Failed to launch Playwright browser.")
                log_callback("This is often due to a missing or misconfigured Playwright installation.")
                log_callback("Please ensure you have run 'pip install playwright' and 'playwright install' from your terminal.")
                log_callback("================= DETAILED ERROR TRACEBACK =================")
                log_callback(traceback.format_exc())
                log_callback("============================================================")
            return

        for acc in accounts:
            if check_stop(stop_event):
                break

            account_id, email, password, twofa_enabled, twofa_type, country_code, phone_number, totp_secret, *_ = acc + (None,) * 9

            status = "PENDING"
            try:
                if log_callback:
                    log_callback("=" * 40)
                    log_callback(f"Starting Login Flow: {email}")

                update_account_status(account_id, "LOGGING_IN")
                
                page.goto("https://accounts.google.com/AddSession", timeout=60000)
                if human_delay(2, 4, stop_event):
                    status = "CANCELLED"
                    break

                auto_skip(page, log_callback, stop_event)

                if is_logged_in(page):
                    if page.locator(f'''div:has-text("{email}")''').count() > 0:
                        if log_callback:
                            log_callback("Session already authenticated.")
                        status = "SUCCESS"
                        update_account_status(account_id, "SUCCESS")
                        continue

                use_another_selector = '''div:has-text("Use another account"), div[role="link"]:has-text("Use another account"), [role="button"]:has-text("Use another account")'''
                if page.locator(use_another_selector).first.is_visible():
                    if log_callback:
                        log_callback("Google 'Choose an account' screen detected.")
                    
                    email_selector = f'''div[data-email="{email}"]'''
                    if page.locator(email_selector).count() > 0 and page.locator(email_selector).first.is_visible():
                        log_callback(f"Account entry for {email} found in list. Clicking it...")
                        human_click(page, email_selector, stop_event)
                    else:
                        log_callback(f"Account {email} not in list. Clicking 'Use another account'...")
                        human_click(page, use_another_selector, stop_event)
                    
                    if human_delay(2.5, 4.5, stop_event):
                        status = "CANCELLED"
                        break

                email_input = page.locator('''input[type="email"]''').first
                if email_input.is_visible():
                    if log_callback:
                        log_callback("Entering email...")
                    email_input.fill("")
                    if human_type(page, '''input[type="email"]''', email, stop_event):
                        status = "CANCELLED"
                        break
                    
                    page.keyboard.press("Enter")
                    if human_delay(3, 5, stop_event):
                        status = "CANCELLED"
                        break

                err = check_login_errors(page)
                if err:
                    if log_callback:
                        log_callback(f"Error after Email: {err}")
                    status = err
                    update_account_status(account_id, err)
                    if err == "CAPTCHA_REQUIRED":
                        wait_for_captcha_solve(page, log_callback, stop_event)
                    continue

                password_input = page.locator('''input[type="password"]''').first
                password_input.wait_for(timeout=5000)

                if password_input.is_visible():
                    if log_callback:
                        log_callback("Entering password...")
                    password_input.fill("")
                    if human_type(page, '''input[type="password"]''', password, stop_event):
                        status = "CANCELLED"
                        break
                    
                    page.keyboard.press("Enter")
                    if human_delay(4, 6, stop_event):
                        status = "CANCELLED"
                        break
                else:
                    if log_callback:
                        log_callback("Password field not found. Captcha or manual action might be blocking.")
                    status = "BLOCKED_OR_CAPTCHA"
                    update_account_status(account_id, "BLOCKED_OR_CAPTCHA")
                    continue
                
                err = check_login_errors(page)
                if err:
                    if log_callback:
                        log_callback(f"Error after Password: {err}")
                    status = err
                    update_account_status(account_id, err)
                    if err == "CAPTCHA_REQUIRED":
                        wait_for_captcha_solve(page, log_callback, stop_event)
                    continue

                auto_skip(page, log_callback, stop_event)

                if is_logged_in(page):
                    status = "SUCCESS"
                elif twofa_enabled:
                    if twofa_type == "SMS":
                        status = handle_sms(page, country_code, phone_number, log_callback, stop_event)
                    elif twofa_type == "Authenticator" and totp_secret:
                        totp_input = page.locator('''input#totpPin, input[type="tel"]''').first
                        totp_input.wait_for(timeout=5000)
                        if totp_input.is_visible():
                            try:
                                totp = pyotp.TOTP(totp_secret.replace(" ", ""))
                                code = totp.now()
                                if log_callback:
                                    log_callback(f"Generating and typing Authenticator (TOTP) code: {code}")
                                human_type(page, '''input#totpPin, input[type="tel"]''', code, stop_event)
                                page.keyboard.press("Enter")
                                if human_delay(4, 7, stop_event):
                                    status = "CANCELLED"
                                    break
                            except Exception as ex:
                                if log_callback:
                                    log_callback(f"TOTP generation failed: {ex}")
                                status = "TOTP_GEN_FAILED"

                        for _ in range(30):
                            if check_stop(stop_event):
                                status = "CANCELLED"; break
                            if is_logged_in(page):
                                status = "SUCCESS"; break
                            time.sleep(3)
                        else:
                            status = "2FA_TIMEOUT"
                    else:
                        if log_callback:
                            log_callback(f"2FA type '{twofa_type}' enabled. Waiting for manual authentication...")
                        for _ in range(40):
                            if check_stop(stop_event):
                                status = "CANCELLED"; break
                            if is_logged_in(page):
                                status = "SUCCESS"; break
                            time.sleep(3)
                        else:
                            status = "2FA_TIMEOUT"
                else:
                    for _ in range(3):
                        if is_logged_in(page):
                            status = "SUCCESS"; break
                        time.sleep(2)
                    else:
                        status = "UNKNOWN_STATE"

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
                    log_callback(f"An unexpected error occurred for {email}: {e}")
                    log_callback("================= DETAILED ERROR TRACEBACK =================")
                    log_callback(traceback.format_exc())
                    log_callback("============================================================")

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
            context.close()
            browser.close()
        except:
            pass
