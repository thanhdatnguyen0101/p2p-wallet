from datetime import datetime, timezone
import hashlib
import os
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DATA_DB = os.path.abspath(
    os.path.join(BASE_DIR, "..", "..", "data", "p2p_wallet.db")
)
BACKEND_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "p2p_wallet.db"))
DATA_DB = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db"))

if os.path.exists(ROOT_DATA_DB):
    DB_PATH = ROOT_DATA_DB
elif os.path.exists(DATA_DB):
    DB_PATH = DATA_DB
else:
    DB_PATH = BACKEND_DB

PORT = 8001


def now_text():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    """Đảm bảo bảng users có cột password_hash"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Cột đã tồn tại
    finally:
        conn.close()


init_db()

app = FastAPI(title="User Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    # Giữ nguyên format lỗi {"error": "..."} như bản http.server cũ
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


class RegisterRequest(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""


class LoginRequest(BaseModel):
    username: str = ""
    password: str = ""


@app.get("/")
def root():
    return {
        "service": "User Service",
        "port": PORT,
        "status": "ONLINE",
        "endpoints": [
            "GET /api/users",
            "POST /api/register",
            "POST /api/login",
        ],
    }


@app.get("/api/users")
def list_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, username, email, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# 1. API ĐĂNG KÝ TÀI KHOẢN MỚI
@app.post("/api/register", status_code=201)
def register(payload: RegisterRequest):
    username = payload.username.strip()
    email = payload.email.strip()
    password = payload.password.strip()

    if not username or not password or not email:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập đầy đủ Username, Email và Mật khẩu",
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Kiểm tra trùng username
    existing = conn.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Tên đăng nhập này đã được sử dụng!")

    # Lưu User vào DB
    pwd_hash = hash_password(password)
    created_time = now_text()
    cur = conn.execute(
        "INSERT INTO users (username, email, password_hash, created_at)"
        " VALUES (?, ?, ?, ?)",
        (username, email, pwd_hash, created_time),
    )
    user_id = cur.lastrowid

    # Tự động tạo Ví chính tặng kèm 1,000,000 VND số dư trải nghiệm
    conn.execute(
        "INSERT INTO wallets (user_id, balance, currency) VALUES (?, 1000000,"
        " 'VND')",
        (user_id,),
    )

    conn.commit()
    conn.close()

    print(
        f"[User Service 8001] Đã tạo vĩnh viễn User '{username}' (ID"
        f" #{user_id}) vào DB!",
        flush=True,
    )
    return {
        "message": "Đăng ký vĩnh viễn thành công!",
        "user": {"id": user_id, "username": username, "email": email},
    }


# 2. API ĐĂNG NHẬP
@app.post("/api/login")
def login(payload: LoginRequest):
    username = payload.username.strip()
    password = payload.password.strip()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    user = conn.execute(
        "SELECT id, username, email, password_hash FROM users WHERE"
        " LOWER(username) = LOWER(?)",
        (username,),
    ).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Tài khoản không tồn tại!")

    # Kiểm tra mật khẩu (Nếu tài khoản cũ chưa có password_hash thì cho phép đăng nhập để không bị lỗi dữ liệu cũ)
    if user["password_hash"] and user["password_hash"] != hash_password(password):
        raise HTTPException(status_code=400, detail="Mật khẩu không chính xác!")

    print(
        f"[User Service 8001] User '{user['username']}' đăng nhập thành"
        " công!",
        flush=True,
    )
    return {
        "message": "Đăng nhập thành công!",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
        },
    }


if __name__ == "__main__":
    import uvicorn

    print(f"[User Service] đang chạy tại http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
