import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT_DIR, "data", "p2p_wallet.db")
passed = 0
failed = 0


def call(method, path, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("[PASS]", name)
    else:
        failed += 1
        print("[FAIL]", name, detail)


def balances():
    _, wallets = call("GET", "/api/wallets")
    return {w["id"]: w["balance"] for w in wallets}


def main():
    before = balances()
    total_before = sum(before.values())
    check("GET /api/wallets co 3 vi", len(before) == 3, before)

    s, r = call("GET", "/api/users/2")
    check("GET /api/users/2 -> 200", s == 200 and r["username"] == "binh", (s, r))

    s, r = call("GET", "/api/users/999")
    check("GET /api/users/999 -> 404", s == 404, (s, r))

    s, r = call("GET", "/khong-ton-tai")
    check("duong dan la -> 404", s == 404, (s, r))

    s, r = call("GET", "/api/transfers")
    check("GET vao route chi co POST -> 405", s == 405, (s, r))

    s, r = call("POST", "/api/transfers", raw=b"{khong phai json")
    check("body JSON loi -> 400", s == 400, (s, r))

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 1, "receiver_wallet_id": 2})
    check("thieu amount -> 400", s == 400, (s, r))

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 1, "receiver_wallet_id": 1, "amount": 1000})
    check("chuyen cho chinh minh -> 400", s == 400, (s, r))

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 1, "receiver_wallet_id": 2, "amount": -5})
    check("amount am -> 400", s == 400, (s, r))

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 1, "receiver_wallet_id": 99, "amount": 1000})
    check("vi nhan khong ton tai -> 404", s == 404, (s, r))

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 1, "receiver_wallet_id": 2, "amount": 999999999})
    check("khong du so du -> 400", s == 400, (s, r))

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 1, "receiver_wallet_id": 2, "amount": 50000})
    check("tao giao dich -> 201 PENDING", s == 201 and r["status"] == "PENDING", (s, r))
    tid, otp = r["transaction_id"], r["demo_otp"]
    check("so du chua doi khi chua xac thuc OTP", balances() == before)

    s, r = call("POST", "/api/transfers/%d/confirm" % tid, {"code": "000000" if otp != "000000" else "111111"})
    check("OTP sai -> 400", s == 400, (s, r))
    check("OTP sai thi so du khong doi", balances() == before)

    s, r = call("POST", "/api/transfers/%d/confirm" % tid, {"code": otp})
    check("OTP dung -> 200 SUCCESS", s == 200 and r["status"] == "SUCCESS", (s, r))

    after = balances()
    check("vi gui bi tru 50000", after[1] == before[1] - 50000, after)
    check("vi nhan duoc cong 50000", after[2] == before[2] + 50000, after)
    check("tong tien he thong khong doi", sum(after.values()) == total_before)

    s, r = call("POST", "/api/transfers/%d/confirm" % tid, {"code": otp})
    check("dung lai OTP -> 409", s == 409, (s, r))
    check("so du khong doi sau khi gui lai", balances() == after)

    s, ledger = call("GET", "/api/ledger")
    rows = [x for x in ledger if x["transaction_id"] == tid]
    types = sorted(x["type"] for x in rows)
    check("sinh 2 dong ledger DEBIT + CREDIT", types == ["CREDIT", "DEBIT"], rows)

    s, r = call("POST", "/api/transfers", {"sender_wallet_id": 2, "receiver_wallet_id": 3, "amount": 10000})
    tid2, otp2 = r["transaction_id"], r["demo_otp"]
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE otp_codes SET expires_at = '2000-01-01 00:00:00' WHERE transaction_id = ?", (tid2,))
    conn.commit()
    conn.close()
    s, r = call("POST", "/api/transfers/%d/confirm" % tid2, {"code": otp2})
    check("OTP het han -> 410", s == 410, (s, r))
    s, r = call("GET", "/api/transactions/%d" % tid2)
    check("giao dich het han chuyen FAILED", r.get("status") == "FAILED", r)
    check("het han thi so du khong doi", balances() == after)

    print("\nKet qua: %d dat, %d loi" % (passed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
