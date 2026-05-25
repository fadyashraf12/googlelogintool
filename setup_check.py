"""
Dependency checker — runs before the main app starts.
Uses only stdlib (tkinter, subprocess, sys) so it works even when
third-party packages are not yet installed.
"""

import sys
import subprocess
import importlib
import tkinter as tk
from tkinter import ttk, messagebox


# ── Packages that must be importable ─────────────────────────────────
import platform as _platform

REQUIRED_PACKAGES = [
    ("customtkinter", "customtkinter"),
    ("pyotp",         "pyotp"),
    ("pyautogui",     "pyautogui"),
    ("pyperclip",     "pyperclip"),
    ("PIL",           "Pillow"),
]

# pygetwindow is Windows-only — add it only when running on Windows
if _platform.system() == "Windows":
    REQUIRED_PACKAGES.append(("pygetwindow", "pygetwindow"))

# pip install names (may differ from import name)
PIP_NAMES = {
    "customtkinter": "customtkinter",
    "pyotp":         "pyotp",
    "pyautogui":     "pyautogui",
    "pygetwindow":   "pygetwindow",
    "pyperclip":     "pyperclip",
    "PIL":           "Pillow",
}


# ─────────────────────────────────────────────────────────────────────
# Progress window (plain tkinter — no third-party deps)
# ─────────────────────────────────────────────────────────────────────

class SetupWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Checking dependencies…")
        self.root.geometry("520x300")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e222b")

        # Try to keep it centred on screen
        self.root.eval('tk::PlaceWindow . center')

        # ── Title ──────────────────────────────────────────────────
        tk.Label(
            self.root,
            text="Google Account Manager",
            font=("Segoe UI", 16, "bold"),
            fg="#3b82f6", bg="#1e222b"
        ).pack(pady=(22, 2))

        tk.Label(
            self.root,
            text="Checking dependencies…",
            font=("Segoe UI", 11),
            fg="#94a3b8", bg="#1e222b"
        ).pack(pady=(0, 14))

        # ── Progress bar ───────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Setup.Horizontal.TProgressbar",
            troughcolor="#151821",
            background="#3b82f6",
            thickness=14,
        )
        self.progress = ttk.Progressbar(
            self.root, style="Setup.Horizontal.TProgressbar",
            orient="horizontal", length=440, mode="determinate"
        )
        self.progress.pack(pady=(0, 12))

        # ── Status label ───────────────────────────────────────────
        self.status_var = tk.StringVar(value="Initialising…")
        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Consolas", 10),
            fg="#38bdf8", bg="#1e222b",
            wraplength=480,
        ).pack(pady=4)

        # ── Log box ────────────────────────────────────────────────
        self.log = tk.Text(
            self.root,
            height=5, width=62,
            font=("Consolas", 9),
            bg="#0f172a", fg="#94a3b8",
            bd=0, relief="flat",
            state="disabled",
        )
        self.log.pack(padx=20, pady=(8, 16))

        self.root.update()

    def set_status(self, text):
        self.status_var.set(text)
        self.root.update()

    def set_progress(self, value):
        self.progress["value"] = value
        self.root.update()

    def append_log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.update()

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────

def _is_importable(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except (ImportError, NotImplementedError, Exception):
        return False


def _pip_install(pip_name, win):
    win.append_log(f"  Installing {pip_name} via pip…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        win.append_log(f"  ERROR: {result.stderr.strip()}")
        return False
    win.append_log(f"  ✔ {pip_name} installed.")
    return True


# ─────────────────────────────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────────────────────────────

def run_setup():
    """
    Check every dependency and auto-fix what can be fixed.
    Returns True  → everything is OK, caller may proceed.
    Returns False → something could not be fixed; app should not start.
    """
    win = SetupWindow()
    steps = len(REQUIRED_PACKAGES)
    completed = 0
    all_ok = True

    for import_name, pip_name in REQUIRED_PACKAGES:
        win.set_status(f"Checking: {pip_name}…")
        win.append_log(f"Checking {pip_name}…")

        if _is_importable(import_name):
            win.append_log(f"  ✔ {pip_name} is installed.")
        else:
            win.append_log(f"  ✗ {pip_name} not found — installing…")
            if not _pip_install(pip_name, win):
                all_ok = False
                win.append_log(f"  ✘ Failed to install {pip_name}.")

        completed += 1
        win.set_progress((completed / steps) * 100)

    win.set_progress(100)

    if all_ok:
        win.set_status("✔ All dependencies ready — launching app…")
        win.append_log("\nAll checks passed. Starting…")
        win.root.after(900, win.close)
        win.root.mainloop()
        return True
    else:
        win.set_status("✘ Some dependencies could not be installed.")
        win.append_log(
            "\nOne or more packages could not be installed automatically.\n"
            "Please run:  pip install -r requirements.txt\n"
            "Then re-launch the app."
        )
        messagebox.showerror(
            "Setup Failed",
            "Some packages could not be installed automatically.\n\n"
            "Open a terminal in the app folder and run:\n\n"
            "    pip install -r requirements.txt\n\n"
            "Then restart the app.",
            parent=win.root,
        )
        win.close()
        return False
