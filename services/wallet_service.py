from contextlib import contextmanager
import os
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db")
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


app = FastAPI(title="Wallet Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


class TransferExecuteRequest(BaseModel):
    sender_wallet_id: int
    receiver_wallet_id: int
    amount: float
    transaction_id: int
    timestamp: str


# Trang trạng thái khi mở http://127.0.0.1:8002/ trên trình duyệt
@app.get("/")
def root():
    return {
        "service": "Wallet Service",
        "port": PORT,
        "status": "ONLINE",
        "description": "Quản lý số dư ví & Sổ cái (Ledger)",
        "endpoints": [
            "GET /api/wallets",
            "GET /api/wallets/:id",
            "GET /api/ledger",
        ],
    }


# API: GET /api/wallets
@app.get("/api/wallets")
def list_wallets():
    conn = open_conn()
    try:
        rows = conn.execute(
            "SELECT w.id, w.user_id, u.username, w.balance, w.currency "
            "FROM wallets w JOIN users u ON u.id = w.user_id ORDER BY w.id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# API: GET /api/wallets/:id
@app.get("/api/wallets/{wallet_id}")
def get_wallet(wallet_id: int):
    conn = open_conn()
    try:
        row = conn.execute(
            "SELECT w.id, w.user_id, u.username, w.balance, w.currency "
            "FROM wallets w JOIN users u ON u.id = w.user_id WHERE w.id = ?",
            (wallet_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ví không tồn tại")
        return dict(row)
    finally:
        conn.close()


# API: GET /api/ledger
@app.get("/api/ledger")
def list_ledger():
    conn = open_conn()
    try:
        rows = conn.execute(
            "SELECT id, wallet_id, transaction_id, type, amount,"
            " balance_after, created_at FROM ledger ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# API: POST /api/wallets/transfer-execute (Chuyển tiền thực sự giữa 2 ví)
@app.post("/api/wallets/transfer-execute")
def transfer_execute(payload: TransferExecuteRequest):
    sender_id = payload.sender_wallet_id
    receiver_id = payload.receiver_wallet_id
    amount = payload.amount
    tx_id = payload.transaction_id
    stamp = payload.timestamp

    with write_tx() as conn:
        s = conn.execute(
            "SELECT id, balance FROM wallets WHERE id = ?", (sender_id,)
        ).fetchone()
        r = conn.execute(
            "SELECT id, balance FROM wallets WHERE id = ?", (receiver_id,)
        ).fetchone()

        if not s or not r:
            raise HTTPException(status_code=404, detail="Ví không tồn tại")
        if s["balance"] < amount:
            raise HTTPException(status_code=400, detail="Số dư không đủ")

        s_after = s["balance"] - amount
        r_after = r["balance"] + amount

        conn.execute(
            "UPDATE wallets SET balance = ? WHERE id = ?", (s_after, sender_id)
        )
        conn.execute(
            "UPDATE wallets SET balance = ? WHERE id = ?", (r_after, receiver_id)
        )

        # Ghi Sổ cái (Ledger)
        conn.execute(
            "INSERT INTO ledger (wallet_id, transaction_id, type, amount,"
            " balance_after, created_at) VALUES (?, ?, 'DEBIT', ?, ?, ?)",
            (sender_id, tx_id, amount, s_after, stamp),
        )
        conn.execute(
            "INSERT INTO ledger (wallet_id, transaction_id, type, amount,"
            " balance_after, created_at) VALUES (?, ?, 'CREDIT', ?, ?, ?)",
            (receiver_id, tx_id, amount, r_after, stamp),
        )

    return {
        "status": "SUCCESS",
        "sender_balance_after": s_after,
        "receiver_balance_after": r_after,
    }


if __name__ == "__main__":
    import uvicorn

    print(f"[Wallet Service] đang chạy tại http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
