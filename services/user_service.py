from datetime import datetime, timezone
import hashlib
import os
import sqlite3
from typing import Optional

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


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_EMAIL = "admin@p2pwallet.local"
DEFAULT_ADMIN_PASSWORD = "Admin@123"


def init_db():
    """Đảm bảo bảng users có cột password_hash, is_admin và có sẵn 1 tài khoản admin"""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Cột đã tồn tại

    try:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Cột đã tồn tại

    # Luôn đảm bảo có đúng 1 tài khoản admin sẵn dùng
    conn.row_factory = sqlite3.Row
    existing_admin = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 LIMIT 1"
    ).fetchone()
    if not existing_admin:
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash,"
            " created_at, is_admin) VALUES (?, ?, ?, ?, 1)",
            (
                DEFAULT_ADMIN_USERNAME,
                DEFAULT_ADMIN_EMAIL,
                hash_password(DEFAULT_ADMIN_PASSWORD),
                now_text(),
            ),
        )
        conn.commit()
        print(
            f"[User Service 8001] Đã tạo tài khoản admin mặc định: "
            f"username='{DEFAULT_ADMIN_USERNAME}' password='{DEFAULT_ADMIN_PASSWORD}'",
            flush=True,
        )

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


class AdminCreateUserRequest(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""
    initial_balance: float = 1000000


class AdminUpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


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
            "POST /api/admin/users",
            "PUT /api/admin/users/:id",
            "DELETE /api/admin/users/:id",
        ],
    }


@app.get("/api/users")
def list_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, username, email, created_at FROM users WHERE"
        " COALESCE(is_admin, 0) = 0 ORDER BY id"
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
        "SELECT id, username, email, password_hash, COALESCE(is_admin, 0) AS"
        " is_admin FROM users WHERE LOWER(username) = LOWER(?)",
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
            "is_admin": bool(user["is_admin"]),
        },
    }


# 3. API ADMIN: TẠO NGƯỜI DÙNG MỚI
@app.post("/api/admin/users", status_code=201)
def admin_create_user(payload: AdminCreateUserRequest):
    username = payload.username.strip()
    email = payload.email.strip()
    password = payload.password.strip()
    initial_balance = payload.initial_balance

    if not username or not email or not password:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập đầy đủ Username, Email và Mật khẩu",
        )
    if initial_balance < 0:
        raise HTTPException(status_code=400, detail="Số dư khởi tạo không được âm")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    existing = conn.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) ="
        " LOWER(?)",
        (username, email),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(
            status_code=400, detail="Username hoặc Email đã được sử dụng!"
        )

    pwd_hash = hash_password(password)
    created_time = now_text()
    cur = conn.execute(
        "INSERT INTO users (username, email, password_hash, created_at)"
        " VALUES (?, ?, ?, ?)",
        (username, email, pwd_hash, created_time),
    )
    user_id = cur.lastrowid

    conn.execute(
        "INSERT INTO wallets (user_id, balance, currency) VALUES (?, ?, 'VND')",
        (user_id, initial_balance),
    )

    conn.commit()
    conn.close()

    print(
        f"[User Service 8001][ADMIN] Đã tạo User '{username}' (ID #{user_id})",
        flush=True,
    )
    return {
        "message": "Tạo người dùng thành công!",
        "user": {
            "id": user_id,
            "username": username,
            "email": email,
            "created_at": created_time,
        },
    }


# 4. API ADMIN: CẬP NHẬT (SỬA) NGƯỜI DÙNG
@app.put("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AdminUpdateUserRequest):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    new_username = (payload.username or user["username"]).strip()
    new_email = (payload.email or user["email"]).strip()

    if not new_username or not new_email:
        conn.close()
        raise HTTPException(
            status_code=400, detail="Username và Email không được để trống"
        )

    dup = conn.execute(
        "SELECT id FROM users WHERE id != ? AND (LOWER(username) = LOWER(?) OR"
        " LOWER(email) = LOWER(?))",
        (user_id, new_username, new_email),
    ).fetchone()
    if dup:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Username hoặc Email đã được sử dụng bởi tài khoản khác!",
        )

    new_password = (payload.password or "").strip()
    if new_password:
        pwd_hash = hash_password(new_password)
        conn.execute(
            "UPDATE users SET username = ?, email = ?, password_hash = ? WHERE id"
            " = ?",
            (new_username, new_email, pwd_hash, user_id),
        )
    else:
        conn.execute(
            "UPDATE users SET username = ?, email = ? WHERE id = ?",
            (new_username, new_email, user_id),
        )

    conn.commit()
    conn.close()

    print(
        f"[User Service 8001][ADMIN] Đã cập nhật User #{user_id} -> "
        f"'{new_username}'",
        flush=True,
    )
    return {
        "message": "Cập nhật người dùng thành công!",
        "user": {"id": user_id, "username": new_username, "email": new_email},
    }


# 5. API ADMIN: XÓA NGƯỜI DÙNG
@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    wallet = conn.execute(
        "SELECT id, balance FROM wallets WHERE user_id = ?", (user_id,)
    ).fetchone()

    if wallet:
        tx_count = conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE sender_wallet_id = ? OR"
            " receiver_wallet_id = ?",
            (wallet["id"], wallet["id"]),
        ).fetchone()["c"]
        if tx_count > 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=(
                    "Không thể xoá: Người dùng đã có lịch sử giao dịch (cần giữ"
                    " lại để đảm bảo tính toàn vẹn của Sổ cái)"
                ),
            )
        if wallet["balance"] and wallet["balance"] > 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Không thể xoá: Ví vẫn còn số dư"
                    f" {wallet['balance']:,.0f} VND. Vui lòng rút hết tiền trước."
                ),
            )
        conn.execute("DELETE FROM wallets WHERE id = ?", (wallet["id"],))

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    print(f"[User Service 8001][ADMIN] Đã xoá User #{user_id}", flush=True)
    return {"message": "Đã xoá người dùng thành công!"}


if __name__ == "__main__":
    import uvicorn

    print(f"[User Service] đang chạy tại http://127.0.0.1:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT)
