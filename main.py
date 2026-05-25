import sys

# ── Dependency check (uses only stdlib — runs before third-party imports) ──
from setup_check import run_setup
if not run_setup():
    sys.exit(1)

# ── Third-party imports (safe to load now that deps are verified) ──────────
import threading
import customtkinter as ctk
import datetime
import subprocess
import config
import chrome_launcher

from database import (
    init_db,
    add_account,
    update_account,
    delete_account,
    get_accounts
)

from login_bot import login_accounts

# Configure customtkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Ensure database is initialized
init_db()


class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Google Account Manager & Login Automator")
        self.geometry("1280x820")
        self.minsize(1100, 700)

        self.account_vars = []
        self.selected_edit_id = None
        self.stop_event = threading.Event()
        self._browser_open = False

        self.build_ui()
        self.after(500, self.poll_browser_status)

    def build_ui(self):
        # Configure layout grid (1 Row, 2 Columns)
        self.grid_columnconfigure(0, weight=4, minsize=420)
        self.grid_columnconfigure(1, weight=6, minsize=650)
        self.grid_rowconfigure(0, weight=1)

        # ==========================
        # LEFT PANEL: TABVIEW
        # ==========================
        left_panel = ctk.CTkFrame(self, corner_radius=15, fg_color="#1e222b")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=15, pady=15)
        left_panel.grid_rowconfigure(0, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        tabview = ctk.CTkTabview(
            left_panel,
            fg_color="#1e222b",
            segmented_button_fg_color="#151821",
            segmented_button_selected_color="#2563eb",
            segmented_button_selected_hover_color="#1d4ed8",
            segmented_button_unselected_color="#151821",
            segmented_button_unselected_hover_color="#1e293b",
            text_color="#e2e8f0",
            corner_radius=10,
        )
        tabview.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        tabview.add("📋  Accounts")
        tabview.add("⚡  Automation")

        # ── TAB 1: ACCOUNTS FORM ─────────────────────────────────────
        tab_acc = tabview.tab("📋  Accounts")
        tab_acc.grid_columnconfigure(0, weight=1)

        # CREDENTIALS section
        cred_frame = ctk.CTkFrame(tab_acc, fg_color="#151821", corner_radius=8)
        cred_frame.pack(fill="x", padx=5, pady=(8, 6))

        ctk.CTkLabel(cred_frame, text="CREDENTIALS",
                     font=("Segoe UI", 11, "bold"), text_color="#64748b"
                     ).pack(anchor="w", padx=12, pady=(8, 2))

        self.email_entry = ctk.CTkEntry(cred_frame, height=38,
                                        placeholder_text="Google Email Address")
        self.email_entry.pack(fill="x", padx=12, pady=4)

        self.password_entry = ctk.CTkEntry(cred_frame, height=38,
                                           placeholder_text="Password", show="*")
        self.password_entry.pack(fill="x", padx=12, pady=4)

        self.show_password = ctk.BooleanVar()
        ctk.CTkCheckBox(cred_frame, text="Show Password",
                        variable=self.show_password,
                        command=self.toggle_password,
                        font=("Segoe UI", 12)
                        ).pack(anchor="w", padx=12, pady=(2, 8))

        # 2FA section
        twofa_frame = ctk.CTkFrame(tab_acc, fg_color="#151821", corner_radius=8)
        twofa_frame.pack(fill="x", padx=5, pady=6)

        ctk.CTkLabel(twofa_frame, text="2-FACTOR AUTHENTICATION",
                     font=("Segoe UI", 11, "bold"), text_color="#64748b"
                     ).pack(anchor="w", padx=12, pady=(8, 2))

        self.twofa_var = ctk.BooleanVar()
        self.twofa_checkbox = ctk.CTkCheckBox(
            twofa_frame, text="Enable 2FA Verification",
            variable=self.twofa_var, command=self.update_phone_fields,
            font=("Segoe UI", 12, "bold"))
        self.twofa_checkbox.pack(anchor="w", padx=12, pady=6)

        type_row = ctk.CTkFrame(twofa_frame, fg_color="transparent")
        type_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(type_row, text="2FA Method:", font=("Segoe UI", 12)).pack(side="left")
        self.twofa_type = ctk.StringVar(value="None")
        self.twofa_menu = ctk.CTkOptionMenu(
            type_row,
            values=["None", "SMS", "Email", "Google Prompt", "Authenticator"],
            variable=self.twofa_type, command=self.update_phone_fields, width=160)
        self.twofa_menu.pack(side="right")

        phone_row = ctk.CTkFrame(twofa_frame, fg_color="transparent")
        phone_row.pack(fill="x", padx=12, pady=4)
        self.country_code = ctk.CTkEntry(phone_row, width=65, height=34,
                                         placeholder_text="+20")
        self.country_code.pack(side="left", padx=(0, 6))
        self.phone_number = ctk.CTkEntry(phone_row, height=34,
                                         placeholder_text="Verification Phone")
        self.phone_number.pack(side="left", fill="x", expand=True)

        self.totp_secret = ctk.CTkEntry(twofa_frame, height=34,
                                        placeholder_text="Authenticator Secret Key (TOTP)")
        self.totp_secret.pack(fill="x", padx=12, pady=(2, 10))

        # Form action buttons
        btn_frame = ctk.CTkFrame(tab_acc, fg_color="transparent")
        btn_frame.pack(fill="x", padx=5, pady=6)

        self.add_btn = ctk.CTkButton(
            btn_frame, text="Add Account", command=self.add_new_account,
            height=40, font=("Segoe UI", 13, "bold"),
            fg_color="#2563eb", hover_color="#1d4ed8")
        self.add_btn.pack(fill="x", pady=3)

        self.update_btn = ctk.CTkButton(
            btn_frame, text="Update Account", command=self.update_selected_account,
            height=40, font=("Segoe UI", 13, "bold"),
            fg_color="#10b981", hover_color="#059669",
            text_color_disabled="#a7f3d0", state="disabled")
        self.update_btn.pack(fill="x", pady=3)

        self.clear_btn = ctk.CTkButton(
            btn_frame, text="Clear Form", command=self.clear_inputs,
            height=34, font=("Segoe UI", 12),
            fg_color="#475569", hover_color="#334155")
        self.clear_btn.pack(fill="x", pady=3)

        # ── TAB 2: AUTOMATION ────────────────────────────────────────
        tab_auto = tabview.tab("⚡  Automation")
        tab_auto.grid_columnconfigure(0, weight=1)

        # STEP 1 — Browser detection
        step1_card = ctk.CTkFrame(tab_auto, fg_color="#151821", corner_radius=10)
        step1_card.pack(fill="x", padx=5, pady=(8, 6))

        ctk.CTkLabel(step1_card, text="STEP 1 — Open Any Browser",
                     font=("Segoe UI", 13, "bold"), text_color="#6366f1"
                     ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(step1_card,
                     text="Open Chrome, Firefox, Brave — any browser — in the\n"
                          "VNC viewer above. The bot will open a new tab in it\n"
                          "and control it with mouse & keyboard.",
                     font=("Segoe UI", 10), text_color="#64748b", justify="left"
                     ).pack(anchor="w", padx=12, pady=(0, 8))

        status_row = ctk.CTkFrame(step1_card, fg_color="#0f172a", corner_radius=6)
        status_row.pack(fill="x", padx=12, pady=(0, 6))

        self.chrome_dot = ctk.CTkLabel(
            status_row, text="●", font=("Segoe UI", 18),
            text_color="#ef4444", width=28)
        self.chrome_dot.pack(side="left", padx=(10, 4), pady=6)

        self.chrome_status_lbl = ctk.CTkLabel(
            status_row,
            text="Waiting for a browser window...",
            font=("Segoe UI", 11), text_color="#f87171", anchor="w")
        self.chrome_status_lbl.pack(side="left", pady=6)

        self.chrome_btn = ctk.CTkButton(
            step1_card, text="🌐  No browser? Launch one here",
            command=self.launch_chrome_browser,
            height=32, font=("Segoe UI", 11),
            fg_color="#1e293b", hover_color="#334155",
            border_width=1, border_color="#475569")
        self.chrome_btn.pack(fill="x", padx=12, pady=(0, 10))

        # STEP 2 — Run automation
        step2_card = ctk.CTkFrame(tab_auto, fg_color="#151821", corner_radius=10)
        step2_card.pack(fill="x", padx=5, pady=6)

        ctk.CTkLabel(step2_card, text="STEP 2 — Run Automation",
                     font=("Segoe UI", 13, "bold"), text_color="#16a34a"
                     ).pack(anchor="w", padx=12, pady=(10, 2))

        ctk.CTkLabel(step2_card,
                     text="Go to the 'Accounts' tab or the right panel,\n"
                          "check the accounts you want, then press Start.",
                     font=("Segoe UI", 10), text_color="#64748b", justify="left"
                     ).pack(anchor="w", padx=12, pady=(0, 8))

        self.start_btn = ctk.CTkButton(
            step2_card, text="▶  Start Automated Login",
            command=self.start_login_process,
            height=44, font=("Segoe UI", 14, "bold"),
            fg_color="#16a34a", hover_color="#15803d",
            text_color_disabled="#4b7a57", state="disabled")
        self.start_btn.pack(fill="x", padx=12, pady=(0, 6))

        self.stop_btn = ctk.CTkButton(
            step2_card, text="⏹  Stop Automation",
            command=self.stop_login_process,
            height=36, font=("Segoe UI", 12, "bold"),
            fg_color="#7f1d1d", hover_color="#991b1b",
            text_color_disabled="#fecaca", state="disabled")
        self.stop_btn.pack(fill="x", padx=12, pady=(0, 12))

        # Settings card
        settings_card = ctk.CTkFrame(tab_auto, fg_color="#151821", corner_radius=10)
        settings_card.pack(fill="x", padx=5, pady=6)

        ctk.CTkLabel(settings_card, text="BOT SETTINGS",
                     font=("Segoe UI", 11, "bold"), text_color="#64748b"
                     ).pack(anchor="w", padx=12, pady=(8, 4))

        ctk.CTkLabel(settings_card,
                     text="Typing speed · Typo simulation · 2FA timeout · Account gap delay",
                     font=("Segoe UI", 10), text_color="#475569", wraplength=340, justify="left"
                     ).pack(anchor="w", padx=12, pady=(0, 6))

        self.settings_btn = ctk.CTkButton(
            settings_card, text="⚙  Open Settings",
            command=self.open_settings,
            height=36, font=("Segoe UI", 12),
            fg_color="#1e293b", hover_color="#334155",
            border_width=1, border_color="#475569")
        self.settings_btn.pack(fill="x", padx=12, pady=(0, 12))

        # Init field states
        self.update_phone_fields()

        # ==========================
        # RIGHT PANEL: GRID & LOGS
        # ==========================
        right_panel = ctk.CTkFrame(self, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=15, pady=15)
        
        right_panel.grid_rowconfigure(0, weight=6)  # Accounts grid (larger)
        right_panel.grid_rowconfigure(1, weight=4)  # Log output
        right_panel.grid_columnconfigure(0, weight=1)

        # --- SAVED ACCOUNTS CONTAINER ---
        accounts_container = ctk.CTkFrame(right_panel, corner_radius=15, fg_color="#1e222b")
        accounts_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        # Header inside accounts container
        acc_header = ctk.CTkFrame(accounts_container, fg_color="transparent")
        acc_header.pack(fill="x", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            acc_header, 
            text="Google Sessions Database", 
            font=("Segoe UI", 20, "bold")
        ).pack(side="left")
        
        self.count_label = ctk.CTkLabel(
            acc_header, 
            text="0 accounts", 
            font=("Segoe UI", 13), 
            text_color="#94a3b8"
        ).pack(side="right", padx=10)

        # Table Header labels
        tbl_hdr = ctk.CTkFrame(accounts_container, fg_color="#151821", height=32, corner_radius=5)
        tbl_hdr.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(tbl_hdr, text="Sel", width=35, font=("Segoe UI", 11, "bold"), text_color="#94a3b8").pack(side="left", padx=5)
        ctk.CTkLabel(tbl_hdr, text="Email Address", width=220, anchor="w", font=("Segoe UI", 11, "bold"), text_color="#94a3b8").pack(side="left", padx=10)
        ctk.CTkLabel(tbl_hdr, text="2FA Status", width=120, anchor="w", font=("Segoe UI", 11, "bold"), text_color="#94a3b8").pack(side="left", padx=10)
        ctk.CTkLabel(tbl_hdr, text="Last Status", width=140, anchor="w", font=("Segoe UI", 11, "bold"), text_color="#94a3b8").pack(side="left", padx=10)
        ctk.CTkLabel(tbl_hdr, text="Operations", font=("Segoe UI", 11, "bold"), text_color="#94a3b8").pack(side="right", padx=20)

        # Scrollable list
        self.accounts_frame = ctk.CTkScrollableFrame(
            accounts_container,
            fg_color="transparent"
        )
        self.accounts_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # --- LIVE LOGS CONTAINER ---
        logs_container = ctk.CTkFrame(right_panel, corner_radius=15, fg_color="#1e222b")
        logs_container.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        
        # Header inside logs container
        log_header = ctk.CTkFrame(logs_container, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=(12, 2))
        ctk.CTkLabel(log_header, text="Console Live Logs", font=("Segoe UI", 16, "bold"), text_color="#3b82f6").pack(side="left")
        
        # Log clear button
        ctk.CTkButton(
            log_header, 
            text="Clear Console", 
            command=self.clear_logs,
            height=24,
            width=100,
            font=("Segoe UI", 11),
            fg_color="#334155",
            hover_color="#475569"
        ).pack(side="right")

        # Text Box
        self.log_box = ctk.CTkTextbox(
            logs_container,
            fg_color="#0f172a",
            text_color="#38bdf8",
            font=("Consolas", 12)
        )
        self.log_box.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        # Initial Load
        self.load_accounts()

    # ==========================
    # INPUT STATE CONTROLS
    # ==========================

    def update_phone_fields(self, value=None):
        is_2fa = self.twofa_var.get()
        t_type = self.twofa_type.get()

        if is_2fa:
            self.twofa_menu.configure(state="normal")
            if t_type == "SMS":
                self.country_code.configure(state="normal", fg_color="#1e293b")
                self.phone_number.configure(state="normal", fg_color="#1e293b")
                self.totp_secret.configure(state="disabled", fg_color="#0f172a")
            elif t_type == "Authenticator":
                self.country_code.configure(state="disabled", fg_color="#0f172a")
                self.phone_number.configure(state="disabled", fg_color="#0f172a")
                self.totp_secret.configure(state="normal", fg_color="#1e293b")
            else:
                self.country_code.configure(state="disabled", fg_color="#0f172a")
                self.phone_number.configure(state="disabled", fg_color="#0f172a")
                self.totp_secret.configure(state="disabled", fg_color="#0f172a")
        else:
            self.twofa_type.set("None")
            self.twofa_menu.configure(state="disabled")
            self.country_code.configure(state="disabled", fg_color="#0f172a")
            self.phone_number.configure(state="disabled", fg_color="#0f172a")
            self.totp_secret.configure(state="disabled", fg_color="#0f172a")

    def toggle_password(self):
        if self.show_password.get():
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    # ==========================
    # CONSOLE LOGS
    # ==========================

    def add_log(self, text):
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
        self.log_box.insert("end", timestamp + text + "\n")
        self.log_box.see("end")

    def clear_logs(self):
        self.log_box.delete("0.0", "end")

    # ==========================
    # ADD & UPDATE CONTROLS
    # ==========================

    def add_new_account(self):
        email = self.email_entry.get().strip()
        password = self.password_entry.get().strip()
        twofa_enabled = self.twofa_var.get()
        twofa_type = self.twofa_type.get()
        c_code = self.country_code.get().strip()
        phone = self.phone_number.get().strip()
        secret = self.totp_secret.get().strip()

        if not email or not password:
            self.add_log("Error: Email and Password cannot be empty.")
            return

        add_account(
            email,
            password,
            twofa_enabled,
            twofa_type,
            c_code,
            phone,
            secret
        )
        self.add_log(f"Successfully added account: {email}")
        self.clear_inputs()
        self.load_accounts()

    def update_selected_account(self):
        if not self.selected_edit_id:
            return

        email = self.email_entry.get().strip()
        password = self.password_entry.get().strip()
        twofa_enabled = self.twofa_var.get()
        twofa_type = self.twofa_type.get()
        c_code = self.country_code.get().strip()
        phone = self.phone_number.get().strip()
        secret = self.totp_secret.get().strip()

        if not email or not password:
            self.add_log("Error: Email and Password cannot be empty.")
            return

        update_account(
            self.selected_edit_id,
            email,
            password,
            twofa_enabled,
            twofa_type,
            c_code,
            phone,
            secret
        )
        
        self.add_log(f"Successfully updated account: {email}")
        self.clear_inputs()
        self.selected_edit_id = None
        self.update_btn.configure(state="disabled")
        self.add_btn.configure(state="normal")
        self.load_accounts()

    def remove_account(self, account_id, email):
        delete_account(account_id)
        self.add_log(f"Deleted account: {email}")
        self.load_accounts()

    def edit_account(self, acc):
        self.selected_edit_id = acc[0]
        
        self.clear_inputs()
        
        self.email_entry.insert(0, acc[1])
        self.password_entry.insert(0, acc[2])
        self.twofa_var.set(bool(acc[3]))
        self.twofa_type.set(acc[4])
        
        if acc[5]:
            self.country_code.insert(0, acc[5])
        if acc[6]:
            self.phone_number.insert(0, acc[6])
        if acc[7]:
            self.totp_secret.insert(0, acc[7])

        self.update_phone_fields()
        
        self.update_btn.configure(state="normal")
        self.add_btn.configure(state="disabled")
        self.add_log(f"Loaded credentials into editor: {acc[1]}")

    def clear_inputs(self):
        self.email_entry.delete(0, "end")
        self.password_entry.delete(0, "end")
        self.country_code.delete(0, "end")
        self.phone_number.delete(0, "end")
        self.totp_secret.delete(0, "end")
        self.twofa_var.set(False)
        self.twofa_type.set("None")
        self.update_phone_fields()
        self.selected_edit_id = None
        self.update_btn.configure(state="disabled")
        self.add_btn.configure(state="normal")

    # ==========================
    # LOAD ACCOUNTS TO GRID
    # ==========================

    def load_accounts(self):
        for widget in self.accounts_frame.winfo_children():
            widget.destroy()

        self.account_vars.clear()
        accounts = get_accounts()

        # Update count label
        # (Must search top levels manually if needed, or count elements in get_accounts)
        self.count_label = f"{len(accounts)} accounts loaded"

        for idx, acc in enumerate(accounts):
            acc_id = acc[0]
            email = acc[1]
            twofa_enabled = acc[3]
            twofa_type = acc[4]
            phone = acc[6]
            totp_secret = acc[7]
            last_status = acc[8]

            # Row container (alternating colors)
            row_bg = "#1b2029" if idx % 2 == 0 else "#151821"
            row = ctk.CTkFrame(self.accounts_frame, fg_color=row_bg, corner_radius=6, height=45)
            row.pack(fill="x", pady=3, padx=2)

            # 1. Selection checkbox
            var = ctk.BooleanVar()
            chk = ctk.CTkCheckBox(
                row, 
                text="", 
                variable=var, 
                command=self.update_login_button, 
                width=24
            )
            chk.pack(side="left", padx=(10, 5), pady=10)

            # 2. Email label
            email_lbl = ctk.CTkLabel(
                row, 
                text=email, 
                font=("Segoe UI", 13, "bold"), 
                width=220, 
                anchor="w"
            )
            email_lbl.pack(side="left", padx=10, pady=10)

            # 3. 2FA configuration
            if twofa_enabled:
                info_2fa = twofa_type
                if twofa_type == "SMS" and phone:
                    info_2fa += f" ({phone})"
                elif twofa_type == "Authenticator" and totp_secret:
                    info_2fa += " (TOTP Setup)"
            else:
                info_2fa = "OFF"
            
            lbl_2fa = ctk.CTkLabel(
                row, 
                text=info_2fa, 
                font=("Segoe UI", 12), 
                width=120, 
                anchor="w",
                text_color="#cbd5e1" if twofa_enabled else "#64748b"
            )
            lbl_2fa.pack(side="left", padx=10, pady=10)

            # 4. Status Badge
            status_text = last_status if last_status else "READY"
            
            # Badge color mapping
            badge_fg = "#2ecc71"  # default green
            if status_text == "READY":
                badge_fg = "#94a3b8"
            elif status_text == "SUCCESS":
                badge_fg = "#2ecc71"
            elif status_text in ["WRONG_PASSWORD", "WRONG_EMAIL", "ACCOUNT_DISABLED", "ERROR"]:
                badge_fg = "#f87171"
            elif status_text in ["LOGGING_IN", "PENDING"]:
                badge_fg = "#facc15"
            elif status_text in ["2FA_TIMEOUT", "BLOCKED_OR_CAPTCHA"]:
                badge_fg = "#fb923c"

            status_lbl = ctk.CTkLabel(
                row, 
                text=status_text, 
                font=("Segoe UI", 12, "bold"), 
                text_color=badge_fg, 
                width=140, 
                anchor="w"
            )
            status_lbl.pack(side="left", padx=10, pady=10)

            # 5. Operation buttons (Edit & Delete)
            op_frame = ctk.CTkFrame(row, fg_color="transparent")
            op_frame.pack(side="right", padx=10, pady=5)

            edit_b = ctk.CTkButton(
                op_frame, 
                text="Edit", 
                width=55, 
                height=26,
                font=("Segoe UI", 11, "bold"),
                fg_color="#334155", 
                hover_color="#475569",
                command=lambda a=acc: self.edit_account(a)
            )
            edit_b.pack(side="left", padx=3)

            delete_b = ctk.CTkButton(
                op_frame, 
                text="Delete", 
                width=55, 
                height=26,
                font=("Segoe UI", 11, "bold"),
                fg_color="#7f1d1d", 
                hover_color="#991b1b",
                command=lambda i=acc_id, e=email: self.remove_account(i, e)
            )
            delete_b.pack(side="left", padx=3)

            self.account_vars.append((var, acc))
        
        self.update_login_button()

    # ==========================
    # LOGIN OPERATION ENGINE
    # ==========================

    def update_login_button(self):
        selected = any(var.get() for var, acc in self.account_vars)
        ready = selected and self._browser_open and not self.stop_event.is_set()
        self.start_btn.configure(state="normal" if ready else "disabled")

    def start_login_process(self):
        selected_accounts = [acc for var, acc in self.account_vars if var.get()]

        if not selected_accounts:
            self.add_log("Error: Select at least one account to log in.")
            return

        self.add_log(f"Launching batch login flow for {len(selected_accounts)} accounts...")
        self.stop_event.clear()

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        def run_thread():
            try:
                login_accounts(selected_accounts, self.add_log, self.stop_event)
            except Exception as e:
                self.add_log(f"Engine Exception: {e}")
            finally:
                self.stop_event.clear()
                self.after(0, self.on_login_finished)

        threading.Thread(target=run_thread, daemon=True).start()

    def stop_login_process(self):
        self.add_log("Requesting cancellation... waiting for bot to stop safely.")
        self.stop_event.set()
        self.stop_btn.configure(state="disabled")

    def on_login_finished(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.load_accounts()
        self.add_log("Automation batch flow ended.")

    def open_settings(self):
        SettingsDialog(self)

    # ==========================
    # BROWSER DETECTION & LAUNCH
    # ==========================

    def poll_browser_status(self):
        """Check every 3 s (background thread) whether a browser window is visible."""
        from login_bot import find_browser_window

        def _check():
            wid = find_browser_window()
            self.after(0, lambda: self._update_browser_status(bool(wid)))

        threading.Thread(target=_check, daemon=True).start()
        self.after(3000, self.poll_browser_status)

    def _update_browser_status(self, is_open: bool):
        prev = self._browser_open
        self._browser_open = is_open

        if is_open:
            self.chrome_dot.configure(text_color="#22c55e")
            self.chrome_status_lbl.configure(
                text="Browser: open and ready ✔",
                text_color="#22c55e")
            self.chrome_btn.configure(
                text="✔  Browser Running",
                fg_color="#14532d", hover_color="#166534")
            if not prev:
                self.add_log("✔ Browser window detected — ready to automate.")
        else:
            self.chrome_dot.configure(text_color="#ef4444")
            self.chrome_status_lbl.configure(
                text="Browser: not detected",
                text_color="#f87171")
            self.chrome_btn.configure(
                text="🌐  Launch Chrome",
                fg_color="#4f46e5", hover_color="#4338ca")
            if prev:
                self.add_log("✘ Browser window closed.")

        self.update_login_button()

    def launch_chrome_browser(self):
        """Open the system default browser (xdg-open), falling back to known binaries."""
        self.add_log("Opening browser...")
        self.chrome_btn.configure(state="disabled", text="Opening…")

        def _do():
            import time, shutil
            from login_bot import find_browser_window

            env = os.environ.copy()
            env.setdefault("DISPLAY", ":99")
            profile_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "chrome-profile")

            try:
                launched = False

                # 1. Try xdg-open (respects the Linux default browser setting)
                if shutil.which("xdg-open"):
                    try:
                        subprocess.Popen(
                            ["xdg-open", "https://google.com"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            env=env, start_new_session=True)
                        self.after(0, lambda: self.add_log(
                            "✔ Opened default browser via system handler."))
                        launched = True
                    except Exception:
                        pass

                # 2. Fallback: try known browsers in order
                if not launched:
                    candidates = [
                        "google-chrome", "google-chrome-stable",
                        "chromium-browser", "chromium",
                        "firefox", "brave-browser",
                        "microsoft-edge",
                    ]
                    exe = next(
                        (shutil.which(c) for c in candidates if shutil.which(c)),
                        None
                    )
                    if not exe:
                        # Last resort: Playwright's bundled Chromium
                        exe, _ = chrome_launcher.find_chrome_executable()

                    if exe:
                        args = [exe]
                        if "chrom" in exe.lower():
                            args += [
                                "--no-sandbox", "--disable-dev-shm-usage",
                                "--disable-gpu", "--no-first-run",
                                f"--user-data-dir={profile_dir}",
                            ]
                        try:
                            subprocess.Popen(
                                args,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                env=env, start_new_session=True)
                            self.after(0, lambda e=exe: self.add_log(
                                f"✔ Launched: {e}"))
                            launched = True
                        except Exception as exc:
                            self.after(0, lambda x=exc: self.add_log(
                                f"✘ Could not launch {exe}: {x}"))
                    else:
                        self.after(0, lambda: self.add_log(
                            "✘ No browser found on this system."))

                if launched:
                    # Wait up to 20 s for a browser window to appear
                    for _ in range(20):
                        time.sleep(1)
                        wid = find_browser_window()
                        if wid:
                            self.after(0, lambda: self._update_browser_status(True))
                            return
                    self.after(0, lambda: self.add_log(
                        "⚠ Browser launched but window not detected yet — "
                        "it will appear after the next status check."))

            finally:
                # Always re-enable the button, no matter what
                self.after(0, lambda: self.chrome_btn.configure(
                    state="normal",
                    text="🌐  No browser? Launch one here"))

        threading.Thread(target=_do, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS DIALOG
# ──────────────────────────────────────────────────────────────────────────────

class SettingsDialog(ctk.CTkToplevel):
    """
    Modal settings window.  All values read from / saved to settings.json
    via the config module so the bot picks them up without a restart.
    """

    _BG       = "#1e222b"
    _CARD     = "#151821"
    _ACCENT   = "#3b82f6"
    _MUTED    = "#64748b"
    _TEXT     = "#e2e8f0"

    def __init__(self, parent):
        super().__init__(parent)
        self.title("⚙  Settings")
        self.geometry("520x640")
        self.resizable(False, False)
        self.configure(fg_color=self._BG)
        self.grab_set()           # make modal
        self.focus_force()

        # Load current settings
        self._s = config.load()

        self._build_ui()
        self._populate()

    # ── Build ──────────────────────────────────────────────────────────

    def _section(self, parent, title):
        """Returns a labelled card frame."""
        card = ctk.CTkFrame(parent, fg_color=self._CARD, corner_radius=10)
        card.pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkLabel(card, text=title,
                     font=("Segoe UI", 11, "bold"),
                     text_color=self._MUTED).pack(anchor="w", padx=12, pady=(8, 2))
        return card

    def _row(self, parent, label, right_widget_fn):
        """Two-column row: label on left, widget on right."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=5)
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 12),
                     text_color=self._TEXT, anchor="w").grid(row=0, column=0, sticky="w")
        widget = right_widget_fn(row)
        widget.grid(row=0, column=1, sticky="e", padx=(8, 0))
        return widget

    def _build_ui(self):
        # ── Title ───────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Settings",
                     font=("Segoe UI", 20, "bold"),
                     text_color=self._ACCENT).pack(pady=(20, 4))
        ctk.CTkLabel(self, text="Changes are applied immediately — no restart needed.",
                     font=("Segoe UI", 10), text_color=self._MUTED).pack(pady=(0, 12))

        # ── 1. CDP Port ─────────────────────────────────────────────
        card1 = self._section(self, "BROWSER CONNECTION")
        port_row = ctk.CTkFrame(card1, fg_color="transparent")
        port_row.pack(fill="x", padx=12, pady=(4, 8))
        port_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(port_row, text="Chrome Debug Port",
                     font=("Segoe UI", 12), text_color=self._TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w")

        self._port_var = ctk.StringVar()
        port_entry = ctk.CTkEntry(port_row, textvariable=self._port_var,
                                  width=90, height=32,
                                  font=("Consolas", 12),
                                  justify="center")
        port_entry.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(card1,
                     text="Chrome must be launched with  --remote-debugging-port=<value>",
                     font=("Segoe UI", 9), text_color=self._MUTED,
                     wraplength=440, justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        # ── 2. Typing Speed ─────────────────────────────────────────
        card2 = self._section(self, "TYPING BEHAVIOUR")

        speed_row = ctk.CTkFrame(card2, fg_color="transparent")
        speed_row.pack(fill="x", padx=12, pady=(4, 4))
        speed_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(speed_row, text="Typing Speed",
                     font=("Segoe UI", 12), text_color=self._TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w")

        self._speed_var = ctk.StringVar(value="normal")
        seg = ctk.CTkSegmentedButton(
            speed_row,
            values=["slow", "normal", "fast"],
            variable=self._speed_var,
            font=("Segoe UI", 11),
            width=200,
        )
        seg.grid(row=0, column=1, sticky="e")

        speed_hints = ctk.CTkFrame(card2, fg_color="transparent")
        speed_hints.pack(fill="x", padx=12, pady=(0, 4))
        for label, hint in [("slow", "100–220 ms/key"),
                             ("normal", "40–140 ms/key"),
                             ("fast", "20–70 ms/key")]:
            ctk.CTkLabel(speed_hints, text=f"{label}: {hint}",
                         font=("Segoe UI", 9), text_color=self._MUTED).pack(side="left", padx=8)

        # Typo simulation toggle
        self._typo_var = ctk.BooleanVar()
        typo_row = ctk.CTkFrame(card2, fg_color="transparent")
        typo_row.pack(fill="x", padx=12, pady=(2, 10))
        ctk.CTkLabel(typo_row, text="Typo simulation (occasional mis-key + backspace)",
                     font=("Segoe UI", 12), text_color=self._TEXT).pack(side="left")
        ctk.CTkSwitch(typo_row, text="", variable=self._typo_var,
                      width=46).pack(side="right")

        # ── 3. 2FA Timeout ──────────────────────────────────────────
        card3 = self._section(self, "2FA WAIT TIMEOUT")

        self._twofa_var = ctk.IntVar(value=120)
        twofa_hdr = ctk.CTkFrame(card3, fg_color="transparent")
        twofa_hdr.pack(fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(twofa_hdr, text="Seconds to wait for manual 2FA",
                     font=("Segoe UI", 12), text_color=self._TEXT).pack(side="left")
        self._twofa_lbl = ctk.CTkLabel(twofa_hdr, text="120 s",
                                        font=("Consolas", 12, "bold"),
                                        text_color=self._ACCENT)
        self._twofa_lbl.pack(side="right")

        ctk.CTkSlider(card3, from_=30, to=300, number_of_steps=27,
                      variable=self._twofa_var,
                      command=lambda v: self._twofa_lbl.configure(text=f"{int(v)} s")
                      ).pack(fill="x", padx=12, pady=(4, 4))

        ctk.CTkLabel(card3,
                     text="Applies to SMS, Email, and Google Prompt 2FA methods.",
                     font=("Segoe UI", 9), text_color=self._MUTED).pack(
            anchor="w", padx=12, pady=(0, 8))

        # ── 4. Account Gap ──────────────────────────────────────────
        card4 = self._section(self, "DELAY BETWEEN ACCOUNTS")

        # Min gap
        min_hdr = ctk.CTkFrame(card4, fg_color="transparent")
        min_hdr.pack(fill="x", padx=12, pady=(4, 0))
        ctk.CTkLabel(min_hdr, text="Minimum gap (seconds)",
                     font=("Segoe UI", 12), text_color=self._TEXT).pack(side="left")
        self._gap_min_lbl = ctk.CTkLabel(min_hdr, text="3 s",
                                          font=("Consolas", 12, "bold"),
                                          text_color=self._ACCENT)
        self._gap_min_lbl.pack(side="right")
        self._gap_min_var = ctk.DoubleVar(value=3.0)
        ctk.CTkSlider(card4, from_=1, to=15, number_of_steps=14,
                      variable=self._gap_min_var,
                      command=lambda v: self._gap_min_lbl.configure(text=f"{int(v)} s")
                      ).pack(fill="x", padx=12, pady=(2, 6))

        # Max gap
        max_hdr = ctk.CTkFrame(card4, fg_color="transparent")
        max_hdr.pack(fill="x", padx=12, pady=(0, 0))
        ctk.CTkLabel(max_hdr, text="Maximum gap (seconds)",
                     font=("Segoe UI", 12), text_color=self._TEXT).pack(side="left")
        self._gap_max_lbl = ctk.CTkLabel(max_hdr, text="7 s",
                                          font=("Consolas", 12, "bold"),
                                          text_color=self._ACCENT)
        self._gap_max_lbl.pack(side="right")
        self._gap_max_var = ctk.DoubleVar(value=7.0)
        ctk.CTkSlider(card4, from_=1, to=30, number_of_steps=29,
                      variable=self._gap_max_var,
                      command=lambda v: self._gap_max_lbl.configure(text=f"{int(v)} s")
                      ).pack(fill="x", padx=12, pady=(2, 10))

        # ── Buttons ─────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(4, 20))

        ctk.CTkButton(btn_row, text="Reset to Defaults",
                      command=self._reset,
                      height=36, font=("Segoe UI", 12),
                      fg_color="#334155", hover_color="#475569",
                      width=160).pack(side="left")

        ctk.CTkButton(btn_row, text="Save Settings",
                      command=self._save,
                      height=36, font=("Segoe UI", 13, "bold"),
                      fg_color=self._ACCENT, hover_color="#2563eb",
                      width=160).pack(side="right")

    # ── Populate / Save / Reset ────────────────────────────────────────

    def _populate(self):
        """Fill all widgets from the loaded settings dict."""
        self._port_var.set(str(self._s.get("cdp_port", 9222)))
        self._speed_var.set(self._s.get("typing_speed", "normal"))
        self._typo_var.set(bool(self._s.get("typo_simulation", True)))

        twofa = int(self._s.get("twofa_timeout", 120))
        self._twofa_var.set(twofa)
        self._twofa_lbl.configure(text=f"{twofa} s")

        gap_min = float(self._s.get("account_gap_min", 3.0))
        gap_max = float(self._s.get("account_gap_max", 7.0))
        self._gap_min_var.set(gap_min)
        self._gap_max_var.set(gap_max)
        self._gap_min_lbl.configure(text=f"{int(gap_min)} s")
        self._gap_max_lbl.configure(text=f"{int(gap_max)} s")

    def _save(self):
        # Validate port
        try:
            port = int(self._port_var.get())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            from tkinter import messagebox
            messagebox.showerror("Invalid Port",
                                 "CDP Port must be a number between 1 and 65535.",
                                 parent=self)
            return

        # Validate gap ordering
        g_min = int(self._gap_min_var.get())
        g_max = int(self._gap_max_var.get())
        if g_min > g_max:
            g_max = g_min   # silently clamp

        settings = {
            "cdp_port":        port,
            "typing_speed":    self._speed_var.get(),
            "typo_simulation": self._typo_var.get(),
            "twofa_timeout":   int(self._twofa_var.get()),
            "account_gap_min": float(g_min),
            "account_gap_max": float(g_max),
        }
        config.save(settings)
        self.destroy()

    def _reset(self):
        self._s = config.reset()
        self._populate()


if __name__ == "__main__":
    app = App()
    app.mainloop()