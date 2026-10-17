import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "data", "p2p_wallet.db")
ADMIN_HTML = os.path.join(ROOT_DIR, "frontend", "admin.html")
HOST = "127.0.0.1"
PORT = 8000
OTP_TTL_MINUTES = 5
MAX_BODY_BYTES = 1024 * 1024


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def now_text(offset_minutes=0):
    moment = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def open_conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql, params=()):
    conn = open_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


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


def positive_int(body, key):
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApiError(400, "%s phai la so nguyen duong" % key)
    return value


def parse_id(raw):
    try:
        return int(raw)
    except ValueError:
        raise ApiError(404, "Id khong hop le")


def send_email(to_wallet_id, content):
    print("[EMAIL -> vi %s] %s" % (to_wallet_id, content), flush=True)


def list_users(params, body):
    return 200, query("SELECT id, username, email, created_at FROM users ORDER BY id")


def get_user(params, body):
    rows = query(
        "SELECT id, username, email, created_at FROM users WHERE id = ?", (params["id"],)
    )
    if not rows:
        raise ApiError(404, "Khong tim thay user")
    return 200, rows[0]


def list_wallets(params, body):
    return 200, query(
        "SELECT w.id, w.user_id, u.username, w.balance, w.currency "
        "FROM wallets w JOIN users u ON u.id = w.user_id ORDER BY w.id"
    )


def get_wallet(params, body):
    rows = query(
        "SELECT w.id, w.user_id, u.username, w.balance, w.currency "
        "FROM wallets w JOIN users u ON u.id = w.user_id WHERE w.id = ?",
        (params["id"],),
    )
    if not rows:
        raise ApiError(404, "Khong tim thay wallet")
    return 200, rows[0]


def list_transactions(params, body):
    return 200, query(
        "SELECT id, sender_wallet_id, receiver_wallet_id, amount, status, created_at "
        "FROM transactions ORDER BY id"
    )


def get_transaction(params, body):
    rows = query(
        "SELECT id, sender_wallet_id, receiver_wallet_id, amount, status, created_at "
        "FROM transactions WHERE id = ?",
        (params["id"],),
    )
    if not rows:
        raise ApiError(404, "Khong tim thay giao dich")
    return 200, rows[0]


def list_ledger(params, body):
    return 200, query(
        "SELECT id, wallet_id, transaction_id, type, amount, balance_after, created_at "
        "FROM ledger ORDER BY id"
    )


def create_transfer(params, body):
    sender_id = positive_int(body, "sender_wallet_id")
    receiver_id = positive_int(body, "receiver_wallet_id")
    amount = positive_int(body, "amount")
    if sender_id == receiver_id:
        raise ApiError(400, "Khong the chuyen tien cho chinh minh")

    code = "%06d" % secrets.randbelow(1000000)
    expires_at = now_text(OTP_TTL_MINUTES)

    with write_tx() as conn:
        sender = conn.execute(
            "SELECT id, balance FROM wallets WHERE id = ?", (sender_id,)
        ).fetchone()
        receiver = conn.execute(
            "SELECT id FROM wallets WHERE id = ?", (receiver_id,)
        ).fetchone()
        if sender is None or receiver is None:
            raise ApiError(404, "Khong tim thay vi gui hoac vi nhan")
        if sender["balance"] < amount:
            raise ApiError(400, "So du khong du")

        cur = conn.execute(
            "INSERT INTO transactions (sender_wallet_id, receiver_wallet_id, amount, status, created_at) "
            "VALUES (?, ?, ?, 'PENDING', ?)",
            (sender_id, receiver_id, amount, now_text()),
        )
        transaction_id = cur.lastrowid
        conn.execute(
            "INSERT INTO otp_codes (transaction_id, code, expires_at, is_used) VALUES (?, ?, ?, 0)",
            (transaction_id, code, expires_at),
        )

    send_email(sender_id, "OTP giao dich %d: %s (het han luc %s UTC)" % (transaction_id, code, expires_at))
    return 201, {
        "transaction_id": transaction_id,
        "status": "PENDING",
        "otp_expires_at": expires_at,
        "demo_otp": code,
    }


def confirm_transfer(params, body):
    transaction_id = parse_id(params["id"])
    code = body.get("code")
    if not isinstance(code, str) or not code:
        raise ApiError(400, "code phai la chuoi khong rong")

    failure = None
    result = None

    with write_tx() as conn:
        txn = conn.execute(
            "SELECT id, sender_wallet_id, receiver_wallet_id, amount, status "
            "FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        if txn is None:
            raise ApiError(404, "Khong tim thay giao dich")
        if txn["status"] != "PENDING":
            raise ApiError(409, "Giao dich da duoc xu ly (%s)" % txn["status"])

        otp = conn.execute(
            "SELECT id, code, expires_at, is_used FROM otp_codes WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if otp is None or otp["is_used"]:
            raise ApiError(409, "OTP khong con hieu luc")

        if otp["expires_at"] < now_text():
            conn.execute(
                "UPDATE transactions SET status = 'FAILED' WHERE id = ?", (transaction_id,)
            )
            failure = ApiError(410, "OTP da het han, giao dich that bai")
        elif not secrets.compare_digest(
            otp["code"].encode("utf-8"), code.encode("utf-8")
        ):
            raise ApiError(400, "OTP khong dung")
        else:
            sender = conn.execute(
                "SELECT id, balance FROM wallets WHERE id = ?", (txn["sender_wallet_id"],)
            ).fetchone()
            receiver = conn.execute(
                "SELECT id, balance FROM wallets WHERE id = ?", (txn["receiver_wallet_id"],)
            ).fetchone()
            amount = txn["amount"]

            if sender["balance"] < amount:
                conn.execute(
                    "UPDATE transactions SET status = 'FAILED' WHERE id = ?", (transaction_id,)
                )
                failure = ApiError(400, "So du khong du, giao dich that bai")
            else:
                sender_after = sender["balance"] - amount
                receiver_after = receiver["balance"] + amount
                stamp = now_text()
                conn.execute(
                    "UPDATE wallets SET balance = ? WHERE id = ?", (sender_after, sender["id"])
                )
                conn.execute(
                    "UPDATE wallets SET balance = ? WHERE id = ?", (receiver_after, receiver["id"])
                )
                conn.execute(
                    "INSERT INTO ledger (wallet_id, transaction_id, type, amount, balance_after, created_at) "
                    "VALUES (?, ?, 'DEBIT', ?, ?, ?)",
                    (sender["id"], transaction_id, amount, sender_after, stamp),
                )
                conn.execute(
                    "INSERT INTO ledger (wallet_id, transaction_id, type, amount, balance_after, created_at) "
                    "VALUES (?, ?, 'CREDIT', ?, ?, ?)",
                    (receiver["id"], transaction_id, amount, receiver_after, stamp),
                )
                conn.execute("UPDATE otp_codes SET is_used = 1 WHERE id = ?", (otp["id"],))
                conn.execute(
                    "UPDATE transactions SET status = 'SUCCESS' WHERE id = ?", (transaction_id,)
                )
                result = {
                    "transaction_id": transaction_id,
                    "status": "SUCCESS",
                    "sender_balance_after": sender_after,
                    "receiver_balance_after": receiver_after,
                }

    if failure is not None:
        raise failure

    send_email(
        txn["sender_wallet_id"],
        "Giao dich %d thanh cong, so du moi: %d" % (transaction_id, result["sender_balance_after"]),
    )
    send_email(
        txn["receiver_wallet_id"],
        "Ban nhan duoc %d, so du moi: %d" % (txn["amount"], result["receiver_balance_after"]),
    )
    return 200, result


ROUTES = [
    ("GET", ["api", "users"], list_users),
    ("GET", ["api", "users", ":id"], get_user),
    ("GET", ["api", "wallets"], list_wallets),
    ("GET", ["api", "wallets", ":id"], get_wallet),
    ("GET", ["api", "transactions"], list_transactions),
    ("GET", ["api", "transactions", ":id"], get_transaction),
    ("GET", ["api", "ledger"], list_ledger),
    ("POST", ["api", "transfers"], create_transfer),
    ("POST", ["api", "transfers", ":id", "confirm"], confirm_transfer),
]


def split_path(raw_path):
    path = raw_path.split("?", 1)[0]
    return [seg for seg in path.split("/") if seg]


def match(method, segments):
    path_exists = False
    for route_method, pattern, handler in ROUTES:
        if len(pattern) != len(segments):
            continue
        params = {}
        ok = True
        for p, s in zip(pattern, segments):
            if p.startswith(":"):
                params[p[1:]] = s
            elif p != s:
                ok = False
                break
        if not ok:
            continue
        path_exists = True
        if route_method == method:
            return handler, params, True
    return None, None, path_exists


class Handler(BaseHTTPRequestHandler):
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

    def send_html(self, path):
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        header = self.headers.get("Content-Length")
        if header is None:
            return {}
        try:
            length = int(header)
        except ValueError:
            raise ApiError(400, "Content-Length khong hop le")
        if length < 0 or length > MAX_BODY_BYTES:
            raise ApiError(413, "Body qua lon")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "Body khong phai JSON hop le")
        if not isinstance(data, dict):
            raise ApiError(400, "Body phai la mot JSON object")
        return data

    def dispatch(self, method):
        segments = split_path(self.path)

        if method == "GET" and segments in ([], ["admin"], ["admin.html"]):
            self.send_html(ADMIN_HTML)
            return

        handler, params, found = match(method, segments)
        if handler is None:
            if found:
                self.send_json(405, {"error": "Method khong duoc ho tro"})
            else:
                self.send_json(404, {"error": "Khong tim thay duong dan"})
            return

        try:
            body = self.read_json_body() if method == "POST" else {}
            status, data = handler(params, body)
        except ApiError as e:
            self.send_json(e.status, {"error": e.message})
            return
        except sqlite3.Error as e:
            self.send_json(500, {"error": "Loi database", "detail": str(e)})
            return
        self.send_json(status, data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors_headers()
        self.end_headers()

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def log_message(self, format, *args):
        print("%s %s" % (self.command, self.path), flush=True)


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit("Chua co p2p_wallet.db, hay chay: python database/init_db.py")
    server = HTTPServer((HOST, PORT), Handler)
    print("Server dang chay tai http://%s:%d" % (HOST, PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
