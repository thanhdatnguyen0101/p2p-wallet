"""Kiểm thử tự động toàn bộ API P2P Wallet (chỉ dùng thư viện chuẩn, không cần cài thêm).

Cách chạy (PowerShell, thư mục gốc dự án):
    py run_all.py          # cửa sổ 1: bật 4 service
    py test_api_demo.py    # cửa sổ 2: chạy toàn bộ kịch bản kiểm thử

Mỗi lần chạy tự tạo user mới nên chạy lại bao nhiêu lần cũng được, không cần reset DB.
"""
import json
import os
import random
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

USER = "http://127.0.0.1:8001"
WALLET = "http://127.0.0.1:8002"
NOTIFY = "http://127.0.0.1:8003"
TRANSFER = "http://127.0.0.1:8000"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "p2p_wallet.db")
SUFFIX = "%d%03d" % (int(time.time()) % 1000000, random.randint(0, 999))

results = []  # (nhóm, tên, đạt?, mong đợi, thực tế)
current_group = ""


def group(title):
    global current_group
    current_group = title
    print("\n=== %s ===" % title)


def check(name, ok, expected, actual):
    results.append((current_group, name, bool(ok), expected, actual))
    print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    if not ok:
        print("         mong đợi: %s | thực tế: %s" % (expected, actual))


def call(method, url, body=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            status, text = res.status, res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8")
    except Exception as e:  # service tắt, hết giờ, ...
        return 0, {"error": str(e)}
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


def err_text(data):
    return data.get("error", data) if isinstance(data, dict) else data


def new_user(tag):
    username = "demo_%s_%s" % (tag, SUFFIX)
    status, _ = call("POST", USER + "/api/register",
                     {"username": username, "email": username + "@example.com", "password": "matkhau123"})
    wallet_id = None
    if status == 201:
        _, wallets = call("GET", WALLET + "/api/wallets")
        wallet_id = next(w["id"] for w in wallets if w["username"] == username)
    return username, wallet_id


def balance(wallet_id):
    return call("GET", "%s/api/wallets/%d" % (WALLET, wallet_id))[1].get("balance")


def make_transfer(sender, receiver, amount):
    return call("POST", TRANSFER + "/api/transfers",
                {"sender_wallet_id": sender, "receiver_wallet_id": receiver, "amount": amount})


def confirm(tx_id, code):
    return call("POST", "%s/api/transfers/%d/confirm" % (TRANSFER, tx_id), {"code": code})


def ledger_rows(tx_id):
    _, rows = call("GET", WALLET + "/api/ledger")
    return [r for r in rows if r["transaction_id"] == tx_id]


def tx_status(tx_id):
    _, rows = call("GET", TRANSFER + "/api/transactions")
    return next((r["status"] for r in rows if r["id"] == tx_id), None)


def test_health():
    group("1. Bốn service chạy độc lập trên 4 cổng")
    for name, url in [("User 8001", USER), ("Wallet 8002", WALLET), ("Notification 8003", NOTIFY),
                      ("Transfer 8000", TRANSFER)]:
        status, _ = call("GET", url + "/")
        check("%s trả 200" % name, status == 200, 200, status)


def test_user_service():
    group("2. User Service: đăng ký và đăng nhập")
    username, wallet_id = new_user("u")
    check("Đăng ký tài khoản mới → 201 và tự tạo ví", wallet_id is not None, "201 + có ví", wallet_id)
    check("Ví mới được tặng 1.000.000 VND", wallet_id and balance(wallet_id) == 1000000, 1000000,
          wallet_id and balance(wallet_id))
    status, data = call("POST", USER + "/api/register",
                        {"username": username, "email": "khac@example.com", "password": "x"})
    check("Đăng ký trùng username → 400", status == 400, 400, status)
    status, _ = call("POST", USER + "/api/register", {"username": "", "email": "", "password": ""})
    check("Đăng ký thiếu thông tin → 400", status == 400, 400, status)
    status, data = call("POST", USER + "/api/login", {"username": username, "password": "matkhau123"})
    check("Đăng nhập đúng → 200", status == 200 and data.get("user", {}).get("username") == username, 200, status)
    status, _ = call("POST", USER + "/api/login", {"username": username, "password": "saimatkhau"})
    check("Đăng nhập sai mật khẩu → 400", status == 400, 400, status)
    status, _ = call("POST", USER + "/api/login", {"username": "khong_ton_tai_xyz", "password": "x"})
    check("Đăng nhập tài khoản không tồn tại → 400", status == 400, 400, status)
    status, data = call("POST", USER + "/api/login", {"username": username, "password": "matkhau123"})
    check("Response đăng nhập không lộ mật khẩu/hash", "password" not in json.dumps(data).lower(), "không có", "có")


def test_wallet_service():
    group("3. Wallet Service: tra cứu ví và sổ cái")
    status, data = call("GET", WALLET + "/api/wallets/1")
    check("Tra cứu ví #1 → 200", status == 200 and "balance" in data, 200, status)
    status, _ = call("GET", WALLET + "/api/wallets/999999")
    check("Tra cứu ví không tồn tại → 404", status == 404, 404, status)
    status, data = call("GET", WALLET + "/api/ledger")
    check("Lấy sổ cái → 200 (danh sách)", status == 200 and isinstance(data, list), 200, status)


def test_happy_path():
    group("4. Luồng chuyển tiền P2P đầy đủ (OTP 2FA + sổ cái)")
    _, a = new_user("a")
    _, b = new_user("b")
    status, data = make_transfer(a, b, 100000)
    otp = data.get("demo_otp") if isinstance(data, dict) else None
    tx = data.get("transaction_id") if isinstance(data, dict) else None
    check("Tạo lệnh chuyển → 201, trạng thái PENDING, có OTP 6 số",
          status == 201 and data.get("status") == "PENDING" and otp and len(otp) == 6 and otp.isdigit(),
          "201 + PENDING + OTP 6 số", (status, data))
    check("Chưa nhập OTP thì tiền chưa bị trừ", balance(a) == 1000000, 1000000, balance(a))
    wrong = "000000" if otp != "000000" else "111111"
    status, data = confirm(tx, wrong)
    check("Nhập sai OTP → 400", status == 400, 400, (status, err_text(data)))
    check("Sai OTP thì giao dịch vẫn PENDING, tiền không đổi",
          tx_status(tx) == "PENDING" and balance(a) == 1000000, "PENDING + 1.000.000", (tx_status(tx), balance(a)))
    status, data = confirm(tx, otp)
    check("Nhập đúng OTP → 200 SUCCESS", status == 200 and data.get("status") == "SUCCESS", 200, (status, data))
    check("Người gửi bị trừ đúng 100.000", balance(a) == 900000, 900000, balance(a))
    check("Người nhận được cộng đúng 100.000", balance(b) == 1100000, 1100000, balance(b))
    check("Tổng tiền hệ thống bảo toàn (900.000 + 1.100.000)", balance(a) + balance(b) == 2000000, 2000000,
          balance(a) + balance(b))
    rows = ledger_rows(tx)
    types = sorted(r["type"] for r in rows)
    check("Sổ cái có đúng 2 bút toán đối ứng DEBIT + CREDIT", types == ["CREDIT", "DEBIT"], ["CREDIT", "DEBIT"], types)
    status, _ = confirm(tx, otp)
    check("Xác nhận lại giao dịch đã xử lý → 400", status == 400, 400, status)
    check("Xác nhận lại không trừ tiền lần hai", balance(a) == 900000, 900000, balance(a))


def test_validation():
    group("5. Kiểm tra dữ liệu đầu vào và nghiệp vụ")
    _, a = new_user("v1")
    _, b = new_user("v2")
    status, data = make_transfer(a, b, 5000000)
    check("Chuyển vượt số dư → 400", status == 400, 400, (status, err_text(data)))
    status, _ = make_transfer(999999, b, 1000)
    check("Ví người gửi không tồn tại → 404", status == 404, 404, status)
    status, data = make_transfer(a, 999999, 1000)
    check("Ví người nhận không tồn tại → 404 hoặc 400", status in (400, 404), "400/404", (status, err_text(data)))
    status, data = make_transfer(a, a, 1000)
    check("Chuyển cho chính mình → 400", status == 400, 400, (status, err_text(data)))
    status, data = make_transfer(a, b, 0)
    check("Số tiền bằng 0 → 400", status == 400, 400, (status, err_text(data)))
    status, data = make_transfer(a, b, -50000)
    check("Số tiền âm → 400 (chặn rút tiền ngược)", status == 400, 400, (status, err_text(data)))
    check("Số dư người gửi không đổi sau các yêu cầu sai", balance(a) == 1000000, 1000000, balance(a))
    status, _ = call("POST", TRANSFER + "/api/transfers",
                     {"sender_wallet_id": a, "receiver_wallet_id": b, "amount": "abc"})
    check("Số tiền không phải số → 400/422", status in (400, 422), "400/422", status)
    status, _ = call("POST", TRANSFER + "/api/transfers", raw=b'{"sender_wallet_id": 1, "amount":')
    check("JSON hỏng (lỗi trong ảnh Swagger) → 400/422", status in (400, 422), "400/422", status)
    status, _ = confirm(999999, "123456")
    check("Xác nhận giao dịch không tồn tại → 400", status == 400, 400, status)
    status, data = make_transfer(a, b, 1000)
    tx = data.get("transaction_id") if isinstance(data, dict) else None
    status, _ = call("POST", "%s/api/transfers/%s/confirm" % (TRANSFER, tx), {})
    check("Xác nhận thiếu mã OTP → 400", status == 400, 400, status)


def test_otp_expiry():
    group("6. OTP hết hạn (ép hết hạn bằng cách sửa DB, khỏi phải chờ 5 phút)")
    if not os.path.exists(DB_PATH):
        print("  (bỏ qua: không thấy %s)" % DB_PATH)
        return
    _, a = new_user("e1")
    _, b = new_user("e2")
    _, data = make_transfer(a, b, 1000)
    tx, otp = data.get("transaction_id"), data.get("demo_otp")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("UPDATE otp_codes SET expires_at = '2000-01-01 00:00:00' WHERE transaction_id = ?", (tx,))
    conn.commit()
    conn.close()
    status, data = confirm(tx, otp)
    check("Nhập đúng OTP nhưng đã hết hạn → 410", status == 410, 410, (status, err_text(data)))
    check("OTP hết hạn thì tiền không bị trừ", balance(a) == 1000000, 1000000, balance(a))


def test_concurrency():
    group("7. Đua lệnh (Race Condition): nhiều request cùng lúc")
    # 7.1 Mười request cùng xác nhận MỘT giao dịch bằng cùng một OTP đúng
    _, a = new_user("c1")
    _, b = new_user("c2")
    _, data = make_transfer(a, b, 100000)
    tx, otp = data["transaction_id"], data["demo_otp"]
    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(lambda _: confirm(tx, otp)[0], range(10)))
    ok = codes.count(200)
    check("10 request cùng xác nhận 1 giao dịch: chỉ 1 request thành công (200)", ok == 1, "1 lần 200", codes)
    check("Người gửi chỉ bị trừ ĐÚNG 1 lần (900.000)", balance(a) == 900000, 900000, balance(a))
    check("Người nhận chỉ được cộng ĐÚNG 1 lần (1.100.000)", balance(b) == 1100000, 1100000, balance(b))
    check("Sổ cái chỉ có 2 dòng cho giao dịch này", len(ledger_rows(tx)) == 2, 2, len(ledger_rows(tx)))

    # 7.2 Năm lệnh 400.000 cùng rút từ ví 1.000.000: chỉ được 2 lệnh, ví không âm
    _, f = new_user("c3")
    _, g = new_user("c4")
    pending = []
    for _ in range(5):
        _, data = make_transfer(f, g, 400000)
        pending.append((data["transaction_id"], data["demo_otp"]))
    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = list(pool.map(lambda p: confirm(p[0], p[1])[0], pending))
    ok = codes.count(200)
    check("5 lệnh 400.000 từ ví 1.000.000 chạy cùng lúc: đúng 2 lệnh thành công", ok == 2, "2 lần 200", codes)
    check("Số dư người gửi không âm và = 200.000", balance(f) == 200000, 200000, balance(f))
    check("Tổng tiền bảo toàn (200.000 + 1.800.000)", balance(f) + balance(g) == 2000000, 2000000,
          balance(f) + balance(g))


def main():
    print("KIỂM THỬ P2P WALLET - %s" % time.strftime("%d/%m/%Y %H:%M:%S"))
    status, _ = call("GET", TRANSFER + "/")
    if status == 0:
        raise SystemExit("Không kết nối được. Hãy chạy 'py run_all.py' ở cửa sổ khác trước.")
    for step in (test_health, test_user_service, test_wallet_service, test_happy_path,
                 test_validation, test_otp_expiry, test_concurrency):
        step()
    passed = sum(1 for r in results if r[2])
    print("\n" + "=" * 60)
    print("KẾT QUẢ: %d/%d đạt" % (passed, len(results)))
    failed = [r for r in results if not r[2]]
    if failed:
        print("\nCÁC CA CHƯA ĐẠT:")
        for grp, name, _, expected, actual in failed:
            print("- [%s] %s\n    mong đợi: %s | thực tế: %s" % (grp, name, expected, actual))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
