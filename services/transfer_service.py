from datetime import datetime, timezone
import json
import os
import sqlite3
from urllib.request import Request, urlopen

from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db")
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
PORT = 8000


def now_text():
  return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def call_http(url, method="GET", body=None):
  req = Request(url, method=method)
  req.add_header("Content-Type", "application/json")
  data = json.dumps(body).encode("utf-8") if body else None
  try:
    with urlopen(req, data=data) as response:
      return response.status, json.loads(response.read().decode("utf-8"))
  except Exception as e:
    if hasattr(e, "read"):
      return e.code, json.loads(e.read().decode("utf-8"))
    raise e


class TransferServiceHandler(BaseHTTPRequestHandler):

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

  def send_file(self, filename, content_type):
    file_path = os.path.join(FRONTEND_DIR, filename)
    if not os.path.exists(file_path):
      self.send_json(404, {"error": f"File {filename} không tồn tại"})
      return
    with open(file_path, "rb") as f:
      body = f.read()
    self.send_response(200)
    self.send_header("Content-Type", content_type)
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

    # Phục vụ Static Frontend
    if path_segs == [] or path_segs == ["index.html"]:
      self.send_file("index.html", "text/html; charset=utf-8")
      return
    if path_segs == ["admin"] or path_segs == ["admin.html"]:
      self.send_file("admin.html", "text/html; charset=utf-8")
      return
    if path_segs == ["style.css"]:
      self.send_file("style.css", "text/css; charset=utf-8")
      return
    if path_segs == ["app.js"]:
      self.send_file("app.js", "application/javascript; charset=utf-8")
      return

    # API: GET /api/transactions
    if path_segs == ["api", "transactions"]:
      conn = sqlite3.connect(DB_PATH)
      conn.row_factory = sqlite3.Row
      rows = conn.execute(
          "SELECT id, sender_wallet_id, receiver_wallet_id, amount, status,"
          " created_at FROM transactions ORDER BY id"
      ).fetchall()
      conn.close()
      self.send_json(200, [dict(r) for r in rows])
      return

    self.send_json(404, {"error": "Endpoint không tồn tại"})

  def do_POST(self):
    path_segs = [s for s in self.path.split("?")[0].split("/") if s]
    length = int(self.headers.get("Content-Length", 0))
    body = json.loads(self.rfile.read(length)) if length > 0 else {}

    # API: POST /api/transfers (Khởi tạo giao dịch)
    if path_segs == ["api", "transfers"]:
      s_id = body.get("sender_wallet_id")
      r_id = body.get("receiver_wallet_id")
      amt = body.get("amount")

      # 1. Gọi Wallet Service (8002) để kiểm tra số dư
      status, wallet = call_http(f"http://127.0.0.1:8002/api/wallets/{s_id}")
      if status != 200:
        self.send_json(status, wallet)
        return
      if wallet["balance"] < amt:
        self.send_json(400, {"error": "Số dư ví không đủ"})
        return

      # 2. Tạo bản ghi giao dịch PENDING
      conn = sqlite3.connect(DB_PATH)
      cur = conn.execute(
          "INSERT INTO transactions (sender_wallet_id, receiver_wallet_id,"
          " amount, status, created_at) VALUES (?, ?, ?, 'PENDING', ?)",
          (s_id, r_id, amt, now_text()),
      )
      tx_id = cur.lastrowid
      conn.commit()
      conn.close()

      # 3. Gọi Notification Service (8003) để sinh OTP
      _, otp_res = call_http(
          "http://127.0.0.1:8003/api/otp/generate",
          method="POST",
          body={"transaction_id": tx_id},
      )

      self.send_json(
          201,
          {
              "transaction_id": tx_id,
              "status": "PENDING",
              "demo_otp": otp_res.get("demo_otp"),
          },
      )
      return

    # API: POST /api/transfers/:id/confirm (Xác nhận OTP và hoàn tất)
    if (
        len(path_segs) == 4
        and path_segs[:2] == ["api", "transfers"]
        and path_segs[3] == "confirm"
    ):
      tx_id = int(path_segs[2])
      code = body.get("code")

      # Lấy giao dịch
      conn = sqlite3.connect(DB_PATH)
      conn.row_factory = sqlite3.Row
      txn = conn.execute(
          "SELECT * FROM transactions WHERE id = ?", (tx_id,)
      ).fetchone()
      conn.close()

      if not txn or txn["status"] != "PENDING":
        self.send_json(400, {"error": "Giao dịch không hợp lệ hoặc đã xử lý"})
        return

      # 1. Gọi Notification Service (8003) để verify OTP
      status, verify_res = call_http(
          "http://127.0.0.1:8003/api/otp/verify",
          method="POST",
          body={"transaction_id": tx_id, "code": code},
      )
      if status != 200:
        self.send_json(status, verify_res)
        return

      # 2. Gọi Wallet Service (8002) để thực thi trừ/cộng tiền
      stamp = now_text()
      w_status, w_res = call_http(
          "http://127.0.0.1:8002/api/wallets/transfer-execute",
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
        self.send_json(w_status, w_res)
        return

      # Cập nhật giao dịch SUCCESS
      conn = sqlite3.connect(DB_PATH)
      conn.execute(
          "UPDATE transactions SET status = 'SUCCESS' WHERE id = ?", (tx_id,)
      )
      conn.commit()
      conn.close()

      self.send_json(
          200,
          {
              "transaction_id": tx_id,
              "status": "SUCCESS",
              "sender_balance_after": w_res.get("sender_balance_after"),
          },
      )
      return


if __name__ == "__main__":
  server = HTTPServer(("127.0.0.1", PORT), TransferServiceHandler)
  print(f"[Transfer Orchestrator] đang chạy tại http://127.0.0.1:{PORT}")
  server.serve_forever()