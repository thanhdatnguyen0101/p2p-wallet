from datetime import datetime, timedelta, timezone
import os
import sqlite3
import sys
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Bắt buộc xuất console UTF-8 trên Windows nếu có
if sys.platform == "win32":
  try:
    sys.stdout.reconfigure(encoding="utf-8")
  except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DATA_DB = os.path.abspath(
    os.path.join(BASE_DIR, "..", "..", "data", "p2p_wallet.db")
)
DATA_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db"))
BACKEND_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "p2p_wallet.db"))

if os.path.exists(ROOT_DATA_DB):
  DB_PATH = ROOT_DATA_DB
elif os.path.exists(DATA_DB):
  DB_PATH = DATA_DB
else:
  DB_PATH = BACKEND_DB

FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))
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
    print(
        f"⚠️ Lỗi tự động cập nhật trạng thái giao dịch hết hạn: {e}", flush=True
    )


def call_http(url, method="GET", body=None):
  try:
    resp = httpx.request(method, url, json=body, timeout=10.0)
    return resp.status_code, resp.json()
  except httpx.HTTPError as e:
    raise HTTPException(status_code=502, detail=f"Lỗi kết nối tới dịch vụ: {e}")


app = FastAPI(title="Transfer Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
  return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


class TransferRequest(BaseModel):
  sender_wallet_id: int
  receiver_wallet_id: int
  amount: float


class ConfirmRequest(BaseModel):
  code: Optional[str] = None


# ----- Phục vụ Static Frontend -----
@app.get("/")
@app.get("/index.html")
def serve_index():
  file_path = os.path.join(FRONTEND_DIR, "index.html")
  if not os.path.exists(file_path):
    raise HTTPException(status_code=404, detail="File index.html không tồn tại")
  return FileResponse(file_path, media_type="text/html; charset=utf-8")


@app.get("/admin")
@app.get("/admin.html")
def serve_admin():
  file_path = os.path.join(FRONTEND_DIR, "admin.html")
  if not os.path.exists(file_path):
    raise HTTPException(status_code=404, detail="File admin.html không tồn tại")
  return FileResponse(file_path, media_type="text/html; charset=utf-8")


@app.get("/style.css")
def serve_css():
  file_path = os.path.join(FRONTEND_DIR, "style.css")
  if not os.path.exists(file_path):
    raise HTTPException(status_code=404, detail="File style.css không tồn tại")
  return FileResponse(file_path, media_type="text/css; charset=utf-8")


@app.get("/app.js")
def serve_js():
  file_path = os.path.join(FRONTEND_DIR, "app.js")
  if not os.path.exists(file_path):
    raise HTTPException(status_code=404, detail="File app.js không tồn tại")
  return FileResponse(file_path, media_type="application/javascript; charset=utf-8")


# API: GET /api/transactions
@app.get("/api/transactions")
def list_transactions():
  # Tự động quét và cập nhật các giao dịch hết hạn trước khi trả về dữ liệu
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
@app.post("/api/transfers", status_code=201)
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
@app.post("/api/transfers/{tx_id}/confirm")
def confirm_transfer(tx_id: int, payload: ConfirmRequest):
  code = payload.code

  # Quét tự động chuyển các giao dịch hết hạn sang FAILED
  auto_update_expired_transactions()

  # Lấy giao dịch
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
    # Nếu xác nhận OTP thất bại/hết hạn, cập nhật trạng thái giao dịch thành FAILED ngay
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


if __name__ == "__main__":
  import uvicorn

  print(
      f"[Transfer Orchestrator] đang chạy tại http://127.0.0.1:{PORT}",
      flush=True,
  )
  uvicorn.run(app, host="127.0.0.1", port=PORT)