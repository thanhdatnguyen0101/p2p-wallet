"""Utility functions and DB helpers for Transfer Service."""
from datetime import datetime, timedelta, timezone
import os
import sqlite3
import httpx
from fastapi import HTTPException

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

FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "frontend"))
PORT = 8000

WALLET_SERVICE_URL = "http://127.0.0.1:8002"
NOTIFICATION_SERVICE_URL = "http://127.0.0.1:8003"

VN_TZ = timezone(timedelta(hours=7))


def now_text():
    return datetime.now(VN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def auto_update_expired_transactions():
    """Tự động cập nhật giao dịch PENDING thành FAILED nếu OTP đã hết hạn hoặc quá 5 phút"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_str = now_text()

        # 1. Cập nhật các giao dịch PENDING có mã OTP hết hạn trong otp_codes
        cursor.execute(
            """
            UPDATE transactions 
            SET status = 'FAILED' 
            WHERE status = 'PENDING' 
              AND id IN (
                  SELECT transaction_id FROM otp_codes 
                  WHERE expires_at < ?
              )
            """,
            (now_str,),
        )

        # 2. Cập nhật các giao dịch PENDING đã quá 5 phút từ thời điểm tạo
        cursor.execute(
            """
            UPDATE transactions 
            SET status = 'FAILED' 
            WHERE status = 'PENDING' 
              AND datetime(created_at, '+5 minutes') < ?
            """,
            (now_str,),
        )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Lỗi tự động cập nhật trạng thái giao dịch hết hạn: {e}", flush=True)


def call_http(url, method="GET", body=None):
    try:
        resp = httpx.request(method, url, json=body, timeout=10.0)
        return resp.status_code, resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối tới dịch vụ: {e}")
