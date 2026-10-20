from datetime import datetime, timedelta, timezone
import os
import secrets
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db")
PORT = 8003


def now_text(offset_minutes=0):
    moment = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


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


class OtpVerifyRequest(BaseModel):
    transaction_id: Optional[int] = None
    code: Optional[str] = None


@app.get("/")
def root():
    return {
        "service": "Notification Service",
        "port": PORT,
        "status": "ONLINE",
        "description": "Dịch vụ xác thực OTP & Thông báo",
        "endpoints": [
            "POST /api/otp/generate",
            "POST /api/otp/verify",
        ],
    }


# API: POST /api/otp/generate
@app.post("/api/otp/generate", status_code=201)
def generate_otp(payload: OtpGenerateRequest):
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
    conn.close()

    return {"demo_otp": code, "expires_at": expires_at}


# API: POST /api/otp/verify
@app.post("/api/otp/verify")
def verify_otp(payload: OtpVerifyRequest):
    tx_id = payload.transaction_id
    input_code = payload.code

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    otp = conn.execute(
        "SELECT id, code, expires_at, is_used FROM otp_codes WHERE"
        " transaction_id = ?",
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

    print(f"[Notification Service] đang chạy tại http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
