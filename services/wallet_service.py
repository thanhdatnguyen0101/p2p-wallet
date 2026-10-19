from contextlib import contextmanager
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "data", "p2p_wallet.db")
PORT = 8002


def open_conn():
  conn = sqlite3.connect(DB_PATH, isolation_level=None)
  conn.row_factory = sqlite3.Row
  conn.execute("PRAGMA foreign_keys = ON")
  return conn


@contextmanager
def write_tx():
  conn = open_conn()
  try:
    conn.execute("BEGIN IMMEDIATE")
    yield conn
    conn.execute("COMMIT")
  except BaseException:
    if conn.in_transaction:
      conn.execute("ROLLBACK")
    raise
  finally:
    conn.close()


class WalletServiceHandler(BaseHTTPRequestHandler):

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

      # Trang trạng thái khi mở http://127.0.0.1:8002/ trên trình duyệt
      if path_segs == []:
        self.send_json(
            200,
            {
                "service": "Wallet Service",
                "port": 8002,
                "status": "ONLINE",
                "description": "Quản lý số dư ví & Sổ cái (Ledger)",
                "endpoints": [
                    "GET /api/wallets",
                    "GET /api/wallets/:id",
                    "GET /api/ledger",
                ],
            },
        )
        return

      conn = open_conn()
      try:
        # API: GET /api/wallets
        if path_segs == ["api", "wallets"]:
          rows = conn.execute(
              "SELECT w.id, w.user_id, u.username, w.balance, w.currency "
              "FROM wallets w JOIN users u ON u.id = w.user_id ORDER BY w.id"
          ).fetchall()
          self.send_json(200, [dict(r) for r in rows])
          return

        # API: GET /api/wallets/:id
        if len(path_segs) == 3 and path_segs[:2] == ["api", "wallets"]:
          row = conn.execute(
              "SELECT w.id, w.user_id, u.username, w.balance, w.currency "
              "FROM wallets w JOIN users u ON u.id = w.user_id WHERE w.id = ?",
              (path_segs[2],),
          ).fetchone()
          if row:
            self.send_json(200, dict(row))
          else:
            self.send_json(404, {"error": "Ví không tồn tại"})
          return

        # API: GET /api/ledger
        if path_segs == ["api", "ledger"]:
          rows = conn.execute(
              "SELECT id, wallet_id, transaction_id, type, amount,"
              " balance_after, created_at FROM ledger ORDER BY id"
          ).fetchall()
          self.send_json(200, [dict(r) for r in rows])
          return
      finally:
        conn.close()

      self.send_json(404, {"error": "Endpoint không tồn tại ở Wallet Service"})

  def do_POST(self):
    path_segs = [s for s in self.path.split("?")[0].split("/") if s]
    length = int(self.headers.get("Content-Length", 0))
    body = json.loads(self.rfile.read(length)) if length > 0 else {}

    # API: POST /api/wallets/transfer-execute (Chuyển tiền thực sự giữa 2 ví)
    if path_segs == ["api", "wallets", "transfer-execute"]:
      sender_id = body.get("sender_wallet_id")
      receiver_id = body.get("receiver_wallet_id")
      amount = body.get("amount")
      tx_id = body.get("transaction_id")
      stamp = body.get("timestamp")

      with write_tx() as conn:
        s = conn.execute(
            "SELECT id, balance FROM wallets WHERE id = ?", (sender_id,)
        ).fetchone()
        r = conn.execute(
            "SELECT id, balance FROM wallets WHERE id = ?", (receiver_id,)
        ).fetchone()

        if not s or not r:
          self.send_json(404, {"error": "Ví không tồn tại"})
          return
        if s["balance"] < amount:
          self.send_json(400, {"error": "Số dư không đủ"})
          return

        s_after = s["balance"] - amount
        r_after = r["balance"] + amount

        conn.execute(
            "UPDATE wallets SET balance = ? WHERE id = ?", (s_after, sender_id)
        )
        conn.execute(
            "UPDATE wallets SET balance = ? WHERE id = ?", (r_after, receiver_id)
        )

        # Ghi Sổ cái (Ledger)
        conn.execute(
            "INSERT INTO ledger (wallet_id, transaction_id, type, amount,"
            " balance_after, created_at) VALUES (?, ?, 'DEBIT', ?, ?, ?)",
            (sender_id, tx_id, amount, s_after, stamp),
        )
        conn.execute(
            "INSERT INTO ledger (wallet_id, transaction_id, type, amount,"
            " balance_after, created_at) VALUES (?, ?, 'CREDIT', ?, ?, ?)",
            (receiver_id, tx_id, amount, r_after, stamp),
        )

      self.send_json(
          200,
          {
              "status": "SUCCESS",
              "sender_balance_after": s_after,
              "receiver_balance_after": r_after,
          },
      )
      return

    self.send_json(404, {"error": "Endpoint không hợp lệ"})


if __name__ == "__main__":
  server = HTTPServer(("127.0.0.1", PORT), WalletServiceHandler)
  print(f"[Wallet Service] đang chạy tại http://127.0.0.1:{PORT}")
  server.serve_forever()