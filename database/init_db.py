import hashlib
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DB_PATH = os.path.join(ROOT_DIR, "data", "p2p_wallet.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def hash_password(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    users = [
        ("an", "an@example.com", hash_password("123456")),
        ("binh", "binh@example.com", hash_password("123456")),
        ("chi", "chi@example.com", hash_password("123456")),
    ]
    conn.executemany(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", users
    )

    # Tài khoản Admin duy nhất (không có ví, chỉ dùng để quản trị)
    conn.execute(
        "INSERT INTO users (username, email, password_hash, is_admin)"
        " VALUES (?, ?, ?, 1)",
        ("admin", "admin@p2pwallet.local", hash_password("Admin@123")),
    )

    wallets = [(1, 900000, "VND"), (2, 550000, "VND"), (3, 350000, "VND")]
    conn.executemany(
        "INSERT INTO wallets (user_id, balance, currency) VALUES (?, ?, ?)", wallets
    )

    transactions = [
        (1, 2, 100000, "SUCCESS"),
        (2, 3, 50000, "SUCCESS"),
        (1, 3, 200000, "PENDING"),
    ]
    conn.executemany(
        "INSERT INTO transactions (sender_wallet_id, receiver_wallet_id, amount, status) VALUES (?, ?, ?, ?)",
        transactions,
    )

    otps = [
        (1, "482913", "2099-01-01 00:00:00", 1),
        (2, "730551", "2099-01-01 00:00:00", 1),
        (3, "119204", "2099-01-01 00:00:00", 0),
    ]
    conn.executemany(
        "INSERT INTO otp_codes (transaction_id, code, expires_at, is_used) VALUES (?, ?, ?, ?)",
        otps,
    )

    ledger = [
        (1, 1, "DEBIT", 100000, 900000),
        (2, 1, "CREDIT", 100000, 600000),
        (2, 2, "DEBIT", 50000, 550000),
        (3, 2, "CREDIT", 50000, 350000),
    ]
    conn.executemany(
        "INSERT INTO ledger (wallet_id, transaction_id, type, amount, balance_after) VALUES (?, ?, ?, ?, ?)",
        ledger,
    )

    conn.commit()
    conn.close()
    print("Da tao", DB_PATH)


if __name__ == "__main__":
    main()
