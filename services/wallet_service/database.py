"""Database and transaction helpers for Wallet Service."""
from contextlib import contextmanager
import os
import sqlite3

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

PORT = 8002


def open_conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def write_tx():
    conn = open_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
