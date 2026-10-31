from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import secrets
import smtplib
import sqlite3
import sys
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Bắt buộc Windows Console xuất dữ liệu chuẩn UTF-8
if sys.platform == "win32":
  try:
    sys.stdout.reconfigure(encoding="utf-8")
  except Exception:
    pass

# CẤU HÌNH GỬI EMAIL SMTP (Có thể truyền qua biến môi trường hoặc sửa trực tiếp)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv(
    "SENDER_EMAIL", "nmthanhvdb2@gmail.com"
)  # Thay bằng Gmail của bạn
SENDER_PASSWORD = os.getenv(
    "SENDER_PASSWORD", "erhk izqa ekfg rqsi"
)  # Thay bằng App Password 16 ký tự của Google

# XỬ LÝ ĐƯỜNG DẪN DATABASE LINH HOẠT
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

PORT = 8003

VN_TZ = timezone(timedelta(hours=7))
def now_text(offset_minutes=0):
  moment = datetime.now(VN_TZ) + timedelta(minutes=offset_minutes)
  return moment.strftime("%Y-%m-%d %H:%M:%S")


def send_otp_email(to_email: str, otp_code: str, tx_id: int):
  """Hàm gửi Email OTP chạy ngầm bằng SMTP"""
  if not to_email or "@" not in to_email:
    print(
        f"⚠️ [Notification 8003] Bỏ qua gửi email do địa chỉ không hợp lệ:"
        f" {to_email}",
        flush=True,
    )
    return

  try:
    msg = MIMEMultipart()
    msg["From"] = f"P2P Wallet Pro <{SENDER_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = f"[{otp_code}] - Mã xác thực giao dịch #{tx_id}"

    body_html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; max-width: 500px; margin: 0 auto;">
            <h2 style="color: #0d6efd; margin-top: 0;">P2P Wallet Pro</h2>
            <p>Bạn vừa thực hiện lệnh chuyển tiền cho giao dịch <b>#{tx_id}</b>. Mã xác thực OTP của bạn là:</p>
            <div style="background-color: #f8f9fa; padding: 15px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #dc3545; border-radius: 8px; margin: 20px 0; border: 1px dashed #dc3545;">
                {otp_code}
            </div>
            <p style="color: #6c757d; font-size: 13px;">Mã này có hiệu lực trong <b>5 phút</b>. Vui lòng không chia sẻ mã này cho bất kỳ ai.</p>
        </div>
        """
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
      server.starttls()
      server.login(SENDER_EMAIL, SENDER_PASSWORD)
      server.send_message(msg)

    print(
        f"📧 [Notification 8003] Đã gửi thành công OTP {otp_code} tới"
        f" {to_email}",
        flush=True,
    )
  except Exception as e:
    print(f"❌ [Notification 8003] Lỗi khi gửi email: {e}", flush=True)


app = FastAPI(title="Notification Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
  return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


class OtpGenerateRequest(BaseModel):
  transaction_id: Optional[int] = None
  recipient_email: Optional[str] = None


class OtpVerifyRequest(BaseModel):
  transaction_id: Optional[int] = None
  code: Optional[str] = None


@app.get("/")
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
      ],
  }


# API: POST /api/otp/generate
@app.post("/api/otp/generate", status_code=201)
def generate_otp(payload: OtpGenerateRequest, background_tasks: BackgroundTasks):
  tx_id = payload.transaction_id
  code = "%06d" % secrets.randbelow(1000000)
  expires_at = now_text(5)

  conn = sqlite3.connect(DB_PATH)
  conn.execute(
      "INSERT INTO otp_codes (transaction_id, code, expires_at, is_used)"
      " VALUES (?, ?, ?, 0)",
      (tx_id, code, expires_at),
  )
  conn.commit()

  # 1. Tìm email của người gửi từ DB nếu không được truyền trực tiếp trong payload
  target_email = payload.recipient_email
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

  conn.close()

  # 2. Đưa tác vụ gửi email vào BackgroundTasks (không gây nghẽn API)
  if target_email:
    background_tasks.add_task(send_otp_email, target_email, code, tx_id)

  print(
      f"🔔 [Notification Service 8003] Đã tạo mã OTP {code} cho Giao dịch"
      f" #{tx_id} -> Email: {target_email}",
      flush=True,
  )

  return {"demo_otp": code, "expires_at": expires_at, "email": target_email}


# API: POST /api/otp/verify
@app.post("/api/otp/verify")
def verify_otp(payload: OtpVerifyRequest):
  tx_id = payload.transaction_id
  input_code = payload.code

  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  otp = conn.execute(
      "SELECT id, code, expires_at, is_used FROM otp_codes WHERE transaction_id"
      " = ? ORDER BY id DESC LIMIT 1",
      (tx_id,),
  ).fetchone()

  if not otp or otp["is_used"]:
    conn.close()
    raise HTTPException(status_code=409, detail="Mã OTP không còn hiệu lực")

  if otp["expires_at"] < now_text():
    conn.close()
    raise HTTPException(status_code=410, detail="Mã OTP đã hết hạn")

  if not secrets.compare_digest(
      otp["code"].encode("utf-8"), str(input_code).encode("utf-8")
  ):
    conn.close()
    raise HTTPException(status_code=400, detail="Mã OTP không đúng")

  conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp["id"],))
  conn.commit()
  conn.close()

  return {"valid": True, "message": "Xác thực OTP thành công"}


if __name__ == "__main__":
  import uvicorn

  print(
      f"[Notification Service] đang chạy tại http://127.0.0.1:{PORT}", flush=True
  )
  uvicorn.run(app, host="127.0.0.1", port=PORT)