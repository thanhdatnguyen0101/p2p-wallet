"""Utility functions and DB helpers for Notification Service."""
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import sqlite3

# CẤU HÌNH GỬI EMAIL SMTP
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "nmthanhvdb2@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "erhk izqa ekfg rqsi")

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

PORT = 8003
VN_TZ = timezone(timedelta(hours=7))


def init_and_migrate_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='otp_codes'").fetchone()
        if schema and "transaction_id INTEGER NOT NULL" in schema[0]:
            conn.execute("PRAGMA foreign_keys=OFF;")
            conn.execute("""
                CREATE TABLE otp_codes_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id INTEGER REFERENCES transactions(id),
                    code TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_used INTEGER NOT NULL DEFAULT 0
                );
            """)
            conn.execute("INSERT INTO otp_codes_new (id, transaction_id, code, expires_at, is_used) SELECT id, transaction_id, code, expires_at, is_used FROM otp_codes;")
            conn.execute("DROP TABLE otp_codes;")
            conn.execute("ALTER TABLE otp_codes_new RENAME TO otp_codes;")
            conn.commit()
            print("✅ [Notification Service] Đã tự động cập nhật bảng otp_codes thành công!", flush=True)
    except Exception as e:
        print(f"⚠️ [Notification Service] Migration DB Warning: {e}", flush=True)
    finally:
        conn.close()


def now_text(offset_minutes=0):
    moment = datetime.now(VN_TZ) + timedelta(minutes=offset_minutes)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def send_otp_email(to_email: str, otp_code: str, tx_id: int):
    if not to_email or "@" not in to_email:
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

        print(f"📧 [Notification 8003] Đã gửi thành công OTP {otp_code} tới {to_email}", flush=True)
    except Exception as e:
        print(f"❌ [Notification 8003] Lỗi khi gửi email: {e}", flush=True)


def send_forgot_password_email(to_email: str, otp_code: str):
    if not to_email or "@" not in to_email:
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = f"P2P Wallet Pro <{SENDER_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = f"[{otp_code}] - Mã OTP khôi phục mật khẩu tài khoản"

        body_html = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; max-width: 500px; margin: 0 auto;">
            <h2 style="color: #0d6efd; margin-top: 0;">P2P Wallet Pro</h2>
            <p>Bạn đã yêu cầu đặt lại mật khẩu cho tài khoản <b>{to_email}</b>. Mã xác thực OTP của bạn là:</p>
            <div style="background-color: #fff3cd; padding: 15px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #856404; border-radius: 8px; margin: 20px 0; border: 1px dashed #ffeeba;">
                {otp_code}
            </div>
            <p style="color: #6c757d; font-size: 13px;">Mã có hiệu lực trong <b>5 phút</b>. Nếu không phải bạn yêu cầu, vui lòng bỏ qua email này.</p>
        </div>
        """
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)

        print(f"📧 [Notification 8003] Đã gửi OTP đặt lại mật khẩu tới {to_email}", flush=True)
    except Exception as e:
        print(f"❌ [Notification 8003] Lỗi gửi email đặt lại mật khẩu: {e}", flush=True)
