"""Router definitions for Transfer Service."""
import os
import sqlite3
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

try:
    from .model import TransferRequest, ConfirmRequest
    from .utils import (
        DB_PATH,
        FRONTEND_DIR,
        PORT,
        WALLET_SERVICE_URL,
        NOTIFICATION_SERVICE_URL,
        now_text,
        auto_update_expired_transactions,
        call_http,
    )
except ImportError:
    from model import TransferRequest, ConfirmRequest
    from utils import (
        DB_PATH,
        FRONTEND_DIR,
        PORT,
        WALLET_SERVICE_URL,
        NOTIFICATION_SERVICE_URL,
        now_text,
        auto_update_expired_transactions,
        call_http,
    )

router = APIRouter()


# ----- Phục vụ Static Frontend -----
@router.get("/")
@router.get("/index.html")
def serve_index():
    file_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File index.html không tồn tại")
    return FileResponse(file_path, media_type="text/html; charset=utf-8")


@router.get("/admin")
@router.get("/admin.html")
def serve_admin():
    file_path = os.path.join(FRONTEND_DIR, "admin.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File admin.html không tồn tại")
    return FileResponse(file_path, media_type="text/html; charset=utf-8")


@router.get("/style.css")
def serve_css():
    file_path = os.path.join(FRONTEND_DIR, "style.css")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File style.css không tồn tại")
    return FileResponse(file_path, media_type="text/css; charset=utf-8")


@router.get("/app.js")
def serve_js():
    file_path = os.path.join(FRONTEND_DIR, "app.js")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File app.js không tồn tại")
    return FileResponse(file_path, media_type="application/javascript; charset=utf-8")


# API: GET /api/transactions
@router.get("/api/transactions")
def list_transactions():
    auto_update_expired_transactions()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, sender_wallet_id, receiver_wallet_id, amount, status,"
        " created_at FROM transactions ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# API: POST /api/transfers (Khởi tạo giao dịch)
@router.post("/api/transfers", status_code=201)
def create_transfer(payload: TransferRequest):
    s_id = payload.sender_wallet_id
    r_id = payload.receiver_wallet_id
    amt = payload.amount

    # 1. Gọi Wallet Service (8002) để kiểm tra số dư
    status, wallet = call_http(f"{WALLET_SERVICE_URL}/api/wallets/{s_id}")
    if status != 200:
        raise HTTPException(
            status_code=status, detail=wallet.get("error", "Lỗi không xác định")
        )
    if wallet["balance"] < amt:
        raise HTTPException(status_code=400, detail="Số dư ví không đủ")

    # 2. Tạo bản ghi giao dịch PENDING
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO transactions (sender_wallet_id, receiver_wallet_id, amount,"
        " status, created_at) VALUES (?, ?, ?, 'PENDING', ?)",
        (s_id, r_id, amt, now_text()),
    )
    tx_id = cur.lastrowid
    conn.commit()
    conn.close()

    # 3. Gọi Notification Service (8003) để sinh OTP
    _, otp_res = call_http(
        f"{NOTIFICATION_SERVICE_URL}/api/otp/generate",
        method="POST",
        body={"transaction_id": tx_id},
    )

    return {
        "transaction_id": tx_id,
        "status": "PENDING",
        "demo_otp": otp_res.get("demo_otp"),
    }


# API: POST /api/transfers/:id/confirm (Xác nhận OTP và hoàn tất)
@router.post("/api/transfers/{tx_id}/confirm")
def confirm_transfer(tx_id: int, payload: ConfirmRequest):
    code = payload.code

    auto_update_expired_transactions()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    txn = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (tx_id,)
    ).fetchone()
    conn.close()

    if not txn:
        raise HTTPException(status_code=404, detail="Giao dịch không tồn tại")

    if txn["status"] == "SUCCESS":
        raise HTTPException(
            status_code=400, detail="Giao dịch này đã được hoàn tất trước đó"
        )

    if txn["status"] == "FAILED":
        raise HTTPException(
            status_code=400,
            detail="Giao dịch đã thất bại hoặc hết hạn OTP, không thể xác nhận",
        )

    # 1. Gọi Notification Service (8003) để verify OTP
    status, verify_res = call_http(
        f"{NOTIFICATION_SERVICE_URL}/api/otp/verify",
        method="POST",
        body={"transaction_id": tx_id, "code": code},
    )
    if status != 200:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE transactions SET status = 'FAILED' WHERE id = ?", (tx_id,)
        )
        conn.commit()
        conn.close()

        err_detail = (
            verify_res.get("error")
            or verify_res.get("detail")
            or "Mã OTP không hợp lệ hoặc đã hết hạn"
        )
        raise HTTPException(status_code=status, detail=err_detail)

    # 2. Gọi Wallet Service (8002) để thực thi trừ/cộng tiền
    stamp = now_text()
    w_status, w_res = call_http(
        f"{WALLET_SERVICE_URL}/api/wallets/transfer-execute",
        method="POST",
        body={
            "sender_wallet_id": txn["sender_wallet_id"],
            "receiver_wallet_id": txn["receiver_wallet_id"],
            "amount": txn["amount"],
            "transaction_id": tx_id,
            "timestamp": stamp,
        },
    )

    if w_status != 200:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE transactions SET status = 'FAILED' WHERE id = ?", (tx_id,)
        )
        conn.commit()
        conn.close()
        raise HTTPException(
            status_code=w_status,
            detail=w_res.get("error", "Lỗi thực thi giao dịch"),
        )

    # Cập nhật giao dịch SUCCESS
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE transactions SET status = 'SUCCESS' WHERE id = ?", (tx_id,)
    )
    conn.commit()
    conn.close()

    return {
        "transaction_id": tx_id,
        "status": "SUCCESS",
        "sender_balance_after": w_res.get("sender_balance_after"),
    }
