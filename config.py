"""
Persistent application settings.
All values are stored in settings.json beside the app.
Call load() to get a dict, save(dict) to persist changes.
All get_*() helpers call load() each time so the bot always
reads the latest values without needing a restart.
"""

import json
import os

SETTINGS_FILE = "settings.json"

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "cdp_port":         9222,
    "twofa_timeout":    120,       # seconds user has to complete manual 2FA
    "typing_speed":     "normal",  # "slow" | "normal" | "fast"
    "typo_simulation":  True,      # occasional wrong-key + backspace
    "account_gap_min":  3.0,       # seconds between accounts (min)
    "account_gap_max":  7.0,       # seconds between accounts (max)
}

# ── Typing speed profiles → (min_delay_s, max_delay_s) per keystroke ─
SPEED_PROFILES: dict = {
    "slow":   (0.10, 0.22),
    "normal": (0.04, 0.14),
    "fast":   (0.02, 0.07),
}

TYPO_RATE_ENABLED  = 0.03   # 3 % chance of a typo when simulation is on
TYPO_RATE_DISABLED = 0.0


# ── I/O ───────────────────────────────────────────────────────────────

def load() -> dict:
    """Return current settings merged over DEFAULTS (safe even if file missing)."""
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULTS)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(DEFAULTS)


def save(settings: dict) -> None:
    """Persist settings dict to disk."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def reset() -> dict:
    """Overwrite settings file with factory defaults and return them."""
    save(DEFAULTS)
    return dict(DEFAULTS)


# ── Convenience getters (used by login_bot.py) ───────────────────────

def get_cdp_endpoint() -> str:
    return f"http://127.0.0.1:{load()['cdp_port']}"


def get_typing_delays() -> tuple[float, float]:
    speed = load().get("typing_speed", "normal")
    return SPEED_PROFILES.get(speed, SPEED_PROFILES["normal"])


def get_typo_rate() -> float:
    return TYPO_RATE_ENABLED if load().get("typo_simulation", True) else TYPO_RATE_DISABLED


def get_twofa_timeout() -> int:
    return int(load().get("twofa_timeout", DEFAULTS["twofa_timeout"]))


def get_account_gap() -> tuple[float, float]:
    s = load()
    return float(s.get("account_gap_min", DEFAULTS["account_gap_min"])), \
           float(s.get("account_gap_max", DEFAULTS["account_gap_max"]))
