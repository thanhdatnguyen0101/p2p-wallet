from datetime import datetime, timedelta, timezone
import json
import os
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db")
PORT = 8003


def now_text(offset_minutes=0):
  moment = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
  return moment.strftime("%Y-%m-%d %H:%M:%S")


class NotificationServiceHandler(BaseHTTPRequestHandler):

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
                "service": "Notification Service",
                "port": 8003,
                "status": "ONLINE",
                "description": "Dịch vụ xác thực OTP & Thông báo",
                "endpoints": [
                    "POST /api/otp/generate",
                    "POST /api/otp/verify",
                ],
            },
        )
        return

      self.send_json(
          404, {"error": "Endpoint không tồn tại ở Notification Service"}
      )
  def do_POST(self):
    path_segs = [s for s in self.path.split("?")[0].split("/") if s]
    length = int(self.headers.get("Content-Length", 0))
    body = json.loads(self.rfile.read(length)) if length > 0 else {}

    # API: POST /api/otp/generate
    if path_segs == ["api", "otp", "generate"]:
      tx_id = body.get("transaction_id")
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

      self.send_json(201, {"demo_otp": code, "expires_at": expires_at})
      return

    # API: POST /api/otp/verify
    if path_segs == ["api", "otp", "verify"]:
      tx_id = body.get("transaction_id")
      input_code = body.get("code")

      conn = sqlite3.connect(DB_PATH)
      conn.row_factory = sqlite3.Row
      otp = conn.execute(
          "SELECT id, code, expires_at, is_used FROM otp_codes WHERE"
          " transaction_id = ?",
          (tx_id,),
      ).fetchone()

      if not otp or otp["is_used"]:
        conn.close()
        self.send_json(409, {"error": "Mã OTP không còn hiệu lực"})
        return

      if otp["expires_at"] < now_text():
        conn.close()
        self.send_json(410, {"error": "Mã OTP đã hết hạn"})
        return

      if not secrets.compare_digest(
          otp["code"].encode("utf-8"), str(input_code).encode("utf-8")
      ):
        conn.close()
        self.send_json(400, {"error": "Mã OTP không đúng"})
        return

      conn.execute(
          "UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp["id"],)
      )
      conn.commit()
      conn.close()

      self.send_json(200, {"valid": True, "message": "Xác thực OTP thành công"})
      return

    self.send_json(404, {"error": "Endpoint không tồn tại"})


if __name__ == "__main__":
  server = HTTPServer(("127.0.0.1", PORT), NotificationServiceHandler)
  print(f"[Notification Service] đang chạy tại http://127.0.0.1:{PORT}")
  server.serve_forever()