"""
Chrome auto-launch helper.

1. is_chrome_debug_running(port)  — check if CDP endpoint is alive
2. find_chrome_executable()       — locate Chrome/Chromium on this OS
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
    """
    Return True if a CDP-capable browser is already listening on *port*.
    Uses only stdlib — safe to call from anywhere.
    """
    try:
        url = f"http://localhost:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
            return bool(data.get("webSocketDebuggerUrl") or data.get("Browser"))
    except Exception:
        return False


# ── Executable discovery ──────────────────────────────────────────────

def _playwright_chromium_path() -> str | None:
    """Return the path to Playwright's bundled Chromium, or None."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            exe = p.chromium.executable_path
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    return None


_LINUX_CANDIDATES = [
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
    "/snap/bin/chromium",
    "/usr/local/bin/chromium",
]

_WINDOWS_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

_MAC_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_chrome_executable() -> str | None:
    """
    Return the path to a usable Chrome/Chromium executable.
    Priority: Playwright bundle → system Chrome → system Chromium.
    """
    # 1. Playwright's own Chromium (always available after setup)
    pw = _playwright_chromium_path()
    if pw:
        return pw

    # 2. Platform-specific candidates
    if sys.platform.startswith("win"):
        candidates = _WINDOWS_CANDIDATES
    elif sys.platform == "darwin":
        candidates = _MAC_CANDIDATES
    else:
        candidates = _LINUX_CANDIDATES

    for candidate in candidates:
        # Try shutil.which for bare names, os.path.isfile for absolute paths
        found = shutil.which(candidate) or (
            candidate if os.path.isfile(candidate) else None
        )
        if found:
            return found

    return None


# ── Launch ───────────────────────────────────────────────────────────

def launch_chrome(port: int = 9222) -> tuple[bool, str]:
    """
    Launch Chrome/Chromium with ``--remote-debugging-port=<port>``.

    Returns (success: bool, message: str).
    If Chrome is already running on *port*, returns (True, "already_running").
    """
    if is_chrome_debug_running(port):
        return True, "already_running"

    exe = find_chrome_executable()
    if not exe:
        return False, (
            "Could not find Chrome or Chromium on this system.\n"
            "Please install Google Chrome and try again."
        )

    flags = [
        exe,
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--window-size=1280,900",
    ]

    # On Linux we need a DISPLAY; if running under Xvfb (:99), pass it along
    env = os.environ.copy()
    if sys.platform.startswith("linux") and not env.get("DISPLAY"):
        env["DISPLAY"] = ":99"

    try:
        # Detach the subprocess so it outlives this process
        kwargs = dict(
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # On Windows, suppress the black console window that would otherwise pop up
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
        subprocess.Popen(flags, **kwargs)
        return True, "launched"
    except Exception as exc:
        return False, f"Failed to launch browser: {exc}"
