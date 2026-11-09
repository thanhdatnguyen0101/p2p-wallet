"""Router definitions for Notification Service."""
import secrets
import sqlite3
from fastapi import APIRouter, BackgroundTasks, HTTPException

try:
    from .model import OtpGenerateRequest, OtpVerifyRequest, OtpVerifyForgotRequest
    from .utils import (
        DB_PATH,
        PORT,
        now_text,
        send_otp_email,
        send_forgot_password_email,
    )
except ImportError:
    from model import OtpGenerateRequest, OtpVerifyRequest, OtpVerifyForgotRequest
    from utils import (
        DB_PATH,
        PORT,
        now_text,
        send_otp_email,
        send_forgot_password_email,
    )

router = APIRouter()


@router.get("/")
def root():
    return {
        "service": "Notification Service",
        "port": PORT,
        "status": "ONLINE 🟢",
        "mode": "REAL_EMAIL_OTP",
        "description": "Dịch vụ xác thực OTP & Thông báo Email thật",
        "endpoints": [
            "POST /api/otp/generate",
            "POST /api/otp/verify",
            "POST /api/otp/verify-forgot",
        ],
    }


@router.post("/api/otp/generate", status_code=201)
def generate_otp(payload: OtpGenerateRequest, background_tasks: BackgroundTasks):
    tx_id = payload.transaction_id
    target_email = payload.recipient_email
    purpose = payload.purpose or "TRANSACTION"
    code = "%06d" % secrets.randbelow(1000000)
    expires_at = now_text(5)

    conn = sqlite3.connect(DB_PATH)

    if not target_email and tx_id:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT u.email FROM users u "
            "JOIN wallets w ON w.user_id = u.id "
            "JOIN transactions t ON t.sender_wallet_id = w.id "
            "WHERE t.id = ?",
            (tx_id,),
        ).fetchone()
        if row and row["email"]:
            target_email = row["email"]

    if purpose == "FORGOT_PASSWORD" and target_email:
        conn.execute(
            "UPDATE otp_codes SET is_used = 1 WHERE transaction_id IS NULL AND is_used = 0"
        )

    conn.execute(
        "INSERT INTO otp_codes (transaction_id, code, expires_at, is_used) VALUES (?, ?, ?, 0)",
        (tx_id, code, expires_at),
    )
    conn.commit()
    conn.close()

    if target_email:
        if purpose == "FORGOT_PASSWORD":
            background_tasks.add_task(send_forgot_password_email, target_email, code)
        else:
            background_tasks.add_task(send_otp_email, target_email, code, tx_id)

    print(
        f"🔔 [Notification Service 8003] Tạo OTP {code} ({purpose}) -> Email: {target_email}",
        flush=True,
    )

    return {"demo_otp": code, "expires_at": expires_at, "email": target_email}


@router.post("/api/otp/verify")
def verify_otp(payload: OtpVerifyRequest):
    tx_id = payload.transaction_id
    input_code = payload.code

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    otp = conn.execute(
        "SELECT id, code, expires_at, is_used FROM otp_codes WHERE transaction_id = ? ORDER BY id DESC LIMIT 1",
        (tx_id,),
    ).fetchone()

    if not otp or otp["is_used"]:
        conn.close()
        raise HTTPException(status_code=409, detail="Mã OTP không còn hiệu lực")

    if otp["expires_at"] < now_text():
        conn.close()
        raise HTTPException(status_code=410, detail="Mã OTP đã hết hạn")

    if not secrets.compare_digest(otp["code"].encode("utf-8"), str(input_code).encode("utf-8")):
        conn.close()
        raise HTTPException(status_code=400, detail="Mã OTP không đúng")

    conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp["id"],))
    conn.commit()
    conn.close()

    return {"valid": True, "message": "Xác thực OTP thành công"}


@router.post("/api/otp/verify-forgot")
def verify_forgot_otp(payload: OtpVerifyForgotRequest):
    input_code = payload.code

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    otp = conn.execute(
        "SELECT id, code, expires_at, is_used FROM otp_codes WHERE transaction_id IS NULL AND is_used = 0 ORDER BY id DESC LIMIT 1"
    ).fetchone()

    if not otp:
        conn.close()
        raise HTTPException(status_code=409, detail="Mã OTP không hợp lệ hoặc đã sử dụng")

    if otp["expires_at"] < now_text():
        conn.close()
        raise HTTPException(status_code=410, detail="Mã OTP đã hết hạn (quá 5 phút)")

    if not secrets.compare_digest(otp["code"].encode("utf-8"), str(input_code).encode("utf-8")):
        conn.close()
        raise HTTPException(status_code=400, detail="Mã OTP không chính xác")

    conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp["id"],))
    conn.commit()
    conn.close()

    return {"valid": True, "message": "Xác thực OTP khôi phục mật khẩu thành công"}
