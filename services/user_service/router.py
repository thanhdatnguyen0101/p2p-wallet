"""Router definitions for User Service."""
import sqlite3
import httpx
from fastapi import APIRouter, HTTPException

try:
    from .model import (
        RegisterRequest,
        LoginRequest,
        ForgotPasswordRequest,
        ResetPasswordRequest,
        AdminCreateUserRequest,
        AdminUpdateUserRequest,
    )
    from .database import (
        DB_PATH,
        PORT,
        NOTIFICATION_SERVICE_URL,
        now_text,
        hash_password,
        get_db_connection,
    )
except ImportError:
    from model import (
        RegisterRequest,
        LoginRequest,
        ForgotPasswordRequest,
        ResetPasswordRequest,
        AdminCreateUserRequest,
        AdminUpdateUserRequest,
    )
    from database import (
        DB_PATH,
        PORT,
        NOTIFICATION_SERVICE_URL,
        now_text,
        hash_password,
        get_db_connection,
    )

router = APIRouter()


@router.get("/")
def root():
    return {
        "service": "User Service",
        "port": PORT,
        "status": "ONLINE",
        "endpoints": [
            "GET /api/users",
            "POST /api/register",
            "POST /api/login",
            "POST /api/forgot-password/request",
            "POST /api/forgot-password/reset",
            "POST /api/admin/users",
            "PUT /api/admin/users/:id",
            "DELETE /api/admin/users/:id",
        ],
    }


@router.get("/api/users")
def list_users():
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT id, username, email, created_at FROM users WHERE COALESCE(is_admin, 0) = 0 ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/api/register", status_code=201)
def register(payload: RegisterRequest):
    username = payload.username.strip()
    email = payload.email.strip()
    password = payload.password.strip()

    if not username or not password or not email:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập đầy đủ Username, Email và Mật khẩu",
        )

    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Tên đăng nhập này đã được sử dụng!")

    pwd_hash = hash_password(password)
    created_time = now_text()
    cur = conn.execute(
        "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (username, email, pwd_hash, created_time),
    )
    user_id = cur.lastrowid

    conn.execute(
        "INSERT INTO wallets (user_id, balance, currency) VALUES (?, 1000000, 'VND')",
        (user_id,),
    )

    conn.commit()
    conn.close()

    return {
        "message": "Đăng ký vĩnh viễn thành công!",
        "user": {"id": user_id, "username": username, "email": email},
    }


@router.post("/api/login")
def login(payload: LoginRequest):
    username = payload.username.strip()
    password = payload.password.strip()

    conn = get_db_connection()
    user = conn.execute(
        "SELECT id, username, email, password_hash, COALESCE(is_admin, 0) AS is_admin FROM users WHERE LOWER(username) = LOWER(?)",
        (username,),
    ).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Tài khoản không tồn tại!")

    if user["password_hash"] and user["password_hash"] != hash_password(password):
        raise HTTPException(status_code=400, detail="Mật khẩu không chính xác!")

    return {
        "message": "Đăng nhập thành công!",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "is_admin": bool(user["is_admin"]),
        },
    }


@router.post("/api/forgot-password/request")
def request_forgot_password(payload: ForgotPasswordRequest):
    email = payload.email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Vui lòng nhập Email!")

    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="Email này chưa được đăng ký trong hệ thống!")

    try:
        resp = httpx.post(
            f"{NOTIFICATION_SERVICE_URL}/api/otp/generate",
            json={"recipient_email": email, "purpose": "FORGOT_PASSWORD"},
            timeout=10.0,
        )
        if resp.status_code not in (200, 201):
            try:
                err_text = resp.json().get("detail") or resp.json().get("error")
            except Exception:
                err_text = resp.text
            raise HTTPException(status_code=resp.status_code, detail=f"Notification error: {err_text}")

        res_data = resp.json()
        return {"message": "Mã OTP đã được gửi đến email của bạn!", "demo_otp": res_data.get("demo_otp")}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Không thể kết nối Notification Service: {e}")


@router.post("/api/forgot-password/reset")
def reset_password(payload: ResetPasswordRequest):
    email = payload.email.strip()
    otp_code = payload.otp_code.strip()
    new_password = payload.new_password.strip()

    if not email or not otp_code or not new_password:
        raise HTTPException(status_code=400, detail="Vui lòng điền đầy đủ Email, Mã OTP và Mật khẩu mới!")

    try:
        resp = httpx.post(
            f"{NOTIFICATION_SERVICE_URL}/api/otp/verify-forgot",
            json={"email": email, "code": otp_code},
            timeout=10.0,
        )
        if resp.status_code != 200:
            try:
                err = resp.json().get("error") or resp.json().get("detail") or "Mã OTP không hợp lệ"
            except Exception:
                err = resp.text
            raise HTTPException(status_code=resp.status_code, detail=err)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Lỗi xác thực OTP: {e}")

    pwd_hash = hash_password(new_password)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET password_hash = ? WHERE LOWER(email) = LOWER(?)", (pwd_hash, email))
    conn.commit()
    conn.close()

    return {"message": "Đặt lại mật khẩu thành công! Vui lòng đăng nhập bằng mật khẩu mới."}


@router.post("/api/admin/users", status_code=201)
def admin_create_user(payload: AdminCreateUserRequest):
    username = payload.username.strip()
    email = payload.email.strip()
    password = payload.password.strip()
    initial_balance = payload.initial_balance

    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đầy đủ Username, Email và Mật khẩu")
    if initial_balance < 0:
        raise HTTPException(status_code=400, detail="Số dư khởi tạo không được âm")

    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
        (username, email),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Username hoặc Email đã được sử dụng!")

    pwd_hash = hash_password(password)
    created_time = now_text()
    cur = conn.execute(
        "INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (username, email, pwd_hash, created_time),
    )
    user_id = cur.lastrowid

    conn.execute(
        "INSERT INTO wallets (user_id, balance, currency) VALUES (?, ?, 'VND')",
        (user_id, initial_balance),
    )

    conn.commit()
    conn.close()

    return {
        "message": "Tạo người dùng thành công!",
        "user": {
            "id": user_id,
            "username": username,
            "email": email,
            "created_at": created_time,
        },
    }


@router.put("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AdminUpdateUserRequest):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    new_username = (payload.username or user["username"]).strip()
    new_email = (payload.email or user["email"]).strip()

    if not new_username or not new_email:
        conn.close()
        raise HTTPException(status_code=400, detail="Username và Email không được để trống")

    dup = conn.execute(
        "SELECT id FROM users WHERE id != ? AND (LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?))",
        (user_id, new_username, new_email),
    ).fetchone()
    if dup:
        conn.close()
        raise HTTPException(status_code=400, detail="Username hoặc Email đã được sử dụng bởi tài khoản khác!")

    new_password = (payload.password or "").strip()
    if new_password:
        pwd_hash = hash_password(new_password)
        conn.execute(
            "UPDATE users SET username = ?, email = ?, password_hash = ? WHERE id = ?",
            (new_username, new_email, pwd_hash, user_id),
        )
    else:
        conn.execute(
            "UPDATE users SET username = ?, email = ? WHERE id = ?",
            (new_username, new_email, user_id),
        )

    conn.commit()
    conn.close()

    return {
        "message": "Cập nhật người dùng thành công!",
        "user": {"id": user_id, "username": new_username, "email": new_email},
    }


@router.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int):
    conn = get_db_connection()
    user = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    wallet = conn.execute("SELECT id, balance FROM wallets WHERE user_id = ?", (user_id,)).fetchone()

    if wallet:
        tx_count = conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE sender_wallet_id = ? OR receiver_wallet_id = ?",
            (wallet["id"], wallet["id"]),
        ).fetchone()["c"]
        if tx_count > 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail="Không thể xoá: Người dùng đã có lịch sử giao dịch (cần giữ lại để đảm bảo tính toàn vẹn của Sổ cái)",
            )
        if wallet["balance"] and wallet["balance"] > 0:
            conn.close()
            raise HTTPException(
                status_code=400,
                detail=f"Không thể xoá: Ví vẫn còn số dư {wallet['balance']:,.0f} VND. Vui lòng rút hết tiền trước.",
            )
        conn.execute("DELETE FROM wallets WHERE id = ?", (wallet["id"],))

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return {"message": "Đã xoá người dùng thành công!"}
