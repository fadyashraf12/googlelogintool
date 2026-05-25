import sqlite3
import datetime

DB_NAME = "accounts.db"


def connect():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        password TEXT,
        twofa_enabled INTEGER,
        twofa_type TEXT,
        country_code TEXT,
        phone_number TEXT
    )
    """)

    # Schema migration: check and add new columns if they do not exist
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]

    new_cols = {
        "totp_secret": "TEXT",
        "last_status": "TEXT",
        "last_login": "TEXT"
    }

    for col_name, col_type in new_cols.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE accounts ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()


def add_account(
    email,
    password,
    twofa_enabled,
    twofa_type,
    country_code,
    phone_number,
    totp_secret=None,
    last_status=None,
    last_login=None
):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO accounts (
        email,
        password,
        twofa_enabled,
        twofa_type,
        country_code,
        phone_number,
        totp_secret,
        last_status,
        last_login
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        email,
        password,
        int(twofa_enabled),
        twofa_type,
        country_code,
        phone_number,
        totp_secret,
        last_status,
        last_login
    ))

    conn.commit()
    conn.close()


def update_account(
    account_id,
    email,
    password,
    twofa_enabled,
    twofa_type,
    country_code,
    phone_number,
    totp_secret=None,
    last_status=None,
    last_login=None
):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE accounts
    SET
        email=?,
        password=?,
        twofa_enabled=?,
        twofa_type=?,
        country_code=?,
        phone_number=?,
        totp_secret=?,
        last_status=?,
        last_login=?
    WHERE id=?
    """, (
        email,
        password,
        int(twofa_enabled),
        twofa_type,
        country_code,
        phone_number,
        totp_secret,
        last_status,
        last_login,
        account_id
    ))

    conn.commit()
    conn.close()


def update_account_status(account_id, status, last_login=None):
    if last_login is None:
        last_login = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE accounts
    SET
        last_status=?,
        last_login=?
    WHERE id=?
    """, (
        status,
        last_login,
        account_id
    ))

    conn.commit()
    conn.close()


def delete_account(account_id):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM accounts WHERE id=?",
        (account_id,)
    )

    conn.commit()
    conn.close()


def get_accounts():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM accounts
    ORDER BY id DESC
    """)

    data = cursor.fetchall()
    conn.close()
    return data