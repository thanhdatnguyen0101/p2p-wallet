"""Database and helper functions for User Service."""
import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DATA_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "data", "p2p_wallet.db"))
DATA_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db"))
BACKEND_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "p2p_wallet.db"))

if os.path.exists(ROOT_DATA_DB):
    DB_PATH = ROOT_DATA_DB
elif os.path.exists(DATA_DB):
    DB_PATH = DATA_DB
else:
    DB_PATH = BACKEND_DB

PORT = 8001
NOTIFICATION_SERVICE_URL = "http://127.0.0.1:8003"

VN_TZ = timezone(timedelta(hours=7))


def now_text():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@p2pwallet.local"
DEFAULT_ADMIN_PASSWORD = "Admin@123"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.row_factory = sqlite3.Row
    existing_admin = conn.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1").fetchone()
    if not existing_admin:
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash, created_at, is_admin) VALUES (?, ?, ?, ?, 1)",
            (
                DEFAULT_ADMIN_USERNAME,
                DEFAULT_ADMIN_EMAIL,
                hash_password(DEFAULT_ADMIN_PASSWORD),
                now_text(),
            ),
        )
        conn.commit()

    conn.close()
