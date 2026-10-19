from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

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


class UserServiceHandler(BaseHTTPRequestHandler):

  def cors_headers(self):
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")

  def send_json(self, status, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.cors_headers()
    self.end_headers()
    self.wfile.write(body)

  def do_OPTIONS(self):
    self.send_response(204)
    self.cors_headers()
    self.end_headers()

  def do_GET(self):
    path_segs = [s for s in self.path.split("?")[0].split("/") if s]

    if path_segs == []:
      self.send_json(
          200,
          {
              "service": "User Service",
              "port": 8001,
              "status": "ONLINE",
              "endpoints": [
                  "GET /api/users",
                  "POST /api/register",
                  "POST /api/login",
              ],
          },
      )
      return

    if path_segs == ["api", "users"]:
      conn = sqlite3.connect(DB_PATH)
      conn.row_factory = sqlite3.Row
      rows = conn.execute(
          "SELECT id, username, email, created_at FROM users ORDER BY id"
      ).fetchall()
      conn.close()
      self.send_json(200, [dict(r) for r in rows])
      return

    self.send_json(404, {"error": "Endpoint không tồn tại ở User Service"})

  def do_POST(self):
    path_segs = [s for s in self.path.split("?")[0].split("/") if s]
    length = int(self.headers.get("Content-Length", 0))
    body = json.loads(self.rfile.read(length)) if length > 0 else {}

    # 1. API ĐĂNG KÝ TÀI KHOẢN MỚI
    if path_segs == ["api", "register"]:
      username = body.get("username", "").strip()
      email = body.get("email", "").strip()
      password = body.get("password", "").strip()

      if not username or not password or not email:
        self.send_json(
            400, {"error": "Vui lòng nhập đầy đủ Username, Email và Mật khẩu"}
        )
        return

      conn = sqlite3.connect(DB_PATH)
      conn.row_factory = sqlite3.Row

      # Kiểm tra trùng username
      existing = conn.execute(
          "SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,)
      ).fetchone()
      if existing:
        conn.close()
        self.send_json(400, {"error": "Tên đăng nhập này đã được sử dụng!"})
        return

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
      self.send_json(
          201,
          {
              "message": "Đăng ký vĩnh viễn thành công!",
              "user": {"id": user_id, "username": username, "email": email},
          },
      )
      return

    # 2. API ĐĂNG NHẬP
    if path_segs == ["api", "login"]:
      username = body.get("username", "").strip()
      password = body.get("password", "").strip()

      conn = sqlite3.connect(DB_PATH)
      conn.row_factory = sqlite3.Row
      user = conn.execute(
          "SELECT id, username, email, password_hash FROM users WHERE"
          " LOWER(username) = LOWER(?)",
          (username,),
      ).fetchone()
      conn.close()

      if not user:
        self.send_json(400, {"error": "Tài khoản không tồn tại!"})
        return

      # Kiểm tra mật khẩu (Nếu tài khoản cũ chưa có password_hash thì cho phép đăng nhập để không bị lỗi dữ liệu cũ)
      if user["password_hash"] and user["password_hash"] != hash_password(
          password
      ):
        self.send_json(400, {"error": "Mật khẩu không chính xác!"})
        return

      print(
          f"[User Service 8001] User '{user['username']}' đăng nhập thành"
          " công!",
          flush=True,
      )
      self.send_json(
          200,
          {
              "message": "Đăng nhập thành công!",
              "user": {
                  "id": user["id"],
                  "username": user["username"],
                  "email": user["email"],
              },
          },
      )
      return

    self.send_json(404, {"error": "Endpoint không tồn tại ở User Service"})


if __name__ == "__main__":
  server = HTTPServer(("127.0.0.1", PORT), UserServiceHandler)
  print(f"[User Service] đang chạy tại http://127.0.0.1:{PORT}")
  server.serve_forever()