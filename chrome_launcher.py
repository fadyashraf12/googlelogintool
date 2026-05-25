"""
Chrome auto-launch helper.

1. is_chrome_debug_running(port)  — check if CDP endpoint is alive
2. find_chrome_executable()       — locate the user's REAL Chrome installation
3. launch_chrome(port)            — open Chrome with --remote-debugging-port
"""

import os
import sys
import subprocess
import urllib.request
import urllib.error
import json
import shutil


# ── CDP health-check ──────────────────────────────────────────────────

def is_chrome_debug_running(port: int = 9222) -> bool:
    """Return True if a CDP-capable browser is already listening on *port*."""
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
            return bool(data.get("webSocketDebuggerUrl") or data.get("Browser"))
    except Exception:
        return False


def check_chrome_debug_detailed(port: int = 9222) -> tuple[bool, str]:
    """
    Like is_chrome_debug_running but returns (connected, detail_message)
    so callers can log exactly what went wrong.
    """
    import socket

    # 1. Is anything listening on the port at all?
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        port_open = True
    except Exception as sock_err:
        return False, f"Port {port} not open: {sock_err}"

    # 2. Port is open — try the CDP HTTP endpoint
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            raw = resp.read()
        data = json.loads(raw)
        if data.get("webSocketDebuggerUrl") or data.get("Browser"):
            return True, f"Connected — {data.get('Browser', 'unknown browser')}"
        return False, f"Port open but CDP response missing fields: {data}"
    except json.JSONDecodeError as je:
        return False, f"Port open but invalid JSON from CDP: {je}"
    except Exception as he:
        return False, f"Port {port} open but HTTP error: {he}"


# ── Executable discovery ──────────────────────────────────────────────

def _windows_chrome_path() -> str | None:
    """
    Find the user's real Google Chrome on Windows.
    Checks: LOCALAPPDATA install, Program Files (x86), Program Files,
    then tries the Windows registry as a fallback.
    """
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    # Try registry
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                key = winreg.OpenKey(
                    hive,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
                )
                path, _ = winreg.QueryValueEx(key, "")
                winreg.CloseKey(key)
                if path and os.path.isfile(path):
                    return path
            except OSError:
                pass
    except ImportError:
        pass

    return None


_LINUX_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
    "/usr/local/bin/chromium",
]

_MAC_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def _playwright_chromium_path() -> str | None:
    """Return the path to Playwright's bundled Chromium (test browser — last resort)."""
    # Check Replit-provided Chromium first (fast, no subprocess needed)
    replit_chromium = os.environ.get("REPLIT_PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
    if replit_chromium and os.path.isfile(replit_chromium):
        return replit_chromium

    # Try reading from playwright's own driver config without starting a full context
    try:
        import playwright._impl._driver as _driver
        driver_path = _driver.compute_driver_executable()
        import subprocess as _sp
        result = _sp.run(
            [str(driver_path), "show-browsers"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "chromium" in line.lower() and os.sep in line:
                candidate = line.strip().split()[-1]
                if os.path.isfile(candidate):
                    return candidate
    except Exception:
        pass

    # Last resort: use the sync API (may be slow)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    return None


def find_chrome_executable() -> tuple[str | None, bool]:
    """
    Return (path, is_real_chrome).

    Priority:
      1. Replit system Chromium (REPLIT_PLAYWRIGHT_CHROMIUM_EXECUTABLE env var)
      2. User's real installed Chrome/Chromium  → is_real_chrome = True
      3. Playwright's bundled Chromium (fallback) → is_real_chrome = False

    Using the real Chrome means the user's actual profile, bookmarks,
    cookies, and sessions are available inside the browser.
    """
    # Priority 1: Replit-provided Chromium
    replit_chromium = os.environ.get("REPLIT_PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
    if replit_chromium and os.path.isfile(replit_chromium):
        return replit_chromium, True

    if sys.platform.startswith("win"):
        path = _windows_chrome_path()
        if path:
            return path, True
    elif sys.platform == "darwin":
        for candidate in _MAC_CANDIDATES:
            if os.path.isfile(candidate):
                return candidate, True
    else:
        for candidate in _LINUX_CANDIDATES:
            found = shutil.which(candidate) or (
                candidate if os.path.isfile(candidate) else None
            )
            if found:
                return found, True

    # Fallback — Playwright's isolated test browser
    pw = _playwright_chromium_path()
    if pw:
        return pw, False

    return None, False


# ── Launch ────────────────────────────────────────────────────────────

def launch_chrome(port: int = 9222) -> tuple[bool, str]:
    """
    Launch the user's real Chrome with --remote-debugging-port=<port>.

    IMPORTANT: Chrome must not already be running when this is called,
    otherwise it hands the args to the existing instance and the debug
    port never opens.  We warn the user in the returned message.

    Returns (success: bool, message: str).
    """
    if is_chrome_debug_running(port):
        return True, "already_running"

    exe, is_real = find_chrome_executable()
    if not exe:
        return False, (
            "Could not find Google Chrome on this system.\n"
            "Please install Google Chrome from https://www.google.com/chrome/ and try again."
        )

    flags = [
        exe,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    # Required flags for running inside a Linux container / sandbox environment
    if sys.platform.startswith("linux"):
        flags += [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]

    env = os.environ.copy()
    if sys.platform.startswith("linux") and not env.get("DISPLAY"):
        env["DISPLAY"] = ":99"

    try:
        kwargs = dict(
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
        subprocess.Popen(flags, **kwargs)

        kind = "your Chrome (with your real profile)" if is_real else "Playwright test browser (real Chrome not found)"
        return True, f"launched:{kind}"
    except Exception as exc:
        return False, f"Failed to launch browser: {exc}"
