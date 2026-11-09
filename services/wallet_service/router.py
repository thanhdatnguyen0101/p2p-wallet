"""Router definitions for Wallet Service."""
from fastapi import APIRouter, HTTPException

try:
    from .model import TransferExecuteRequest
    from .database import PORT, open_conn, write_tx
except ImportError:
    from model import TransferExecuteRequest
    from database import PORT, open_conn, write_tx

router = APIRouter()


@router.get("/")
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


@router.get("/api/wallets")
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


@router.get("/api/wallets/{wallet_id}")
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


@router.get("/api/ledger")
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


@router.post("/api/wallets/transfer-execute")
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
