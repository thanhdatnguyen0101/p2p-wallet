# P2P Wallet Transfer

Đồ án giữa kỳ môn Kiến trúc Hướng Dịch Vụ (504070) - HK1/2026-2027, TDTU.

Ví điện tử chuyển tiền ngang hàng: người dùng chuyển tiền giữa hai ví, giao dịch được xác thực bằng OTP, mọi biến động số dư đều được ghi vào sổ cái (Ledger).

Giai đoạn hiện tại: API viết bằng Python thuần (`http.server` + `sqlite3`), không dùng framework.

## Yêu cầu

- Python 3.8 trở lên
- Không cần cài thư viện ngoài

## Cấu trúc thư mục

```
p2p-wallet/
├── backend/
│   └── server.py          HTTP server thuần: routing, parse JSON, API, transaction
├── database/
│   ├── schema.sql         Định nghĩa 5 bảng theo ERD
│   └── init_db.py         Tạo database và nạp dữ liệu mẫu
├── frontend/
│   └── admin.html         Trang admin: gọi API và hiển thị bảng
├── tests/
│   └── test_api.py        Test tự động cho toàn bộ API
├── data/                  Chứa p2p_wallet.db (được tạo khi chạy, không đưa lên git)
├── docs/
│   ├── erd.mmd            Mã Mermaid của ERD
│   ├── lenh_test_nhanh.txt  Danh sách lệnh demo
│   ├── diagrams/          Use Case, DFD, Microservices Architecture Diagram
│   └── report/            Báo cáo
├── .gitignore
└── README.md
```

## Cài đặt và chạy

Mở terminal tại thư mục gốc của dự án.

Windows:

```
python database/init_db.py
python backend/server.py
```

macOS / Linux:

```
python3 database/init_db.py
python3 backend/server.py
```

Server chạy tại http://127.0.0.1:8000. Mở http://127.0.0.1:8000/admin để xem trang admin.

## Chạy test

Giữ server đang chạy, mở terminal thứ hai tại thư mục gốc:

```
python tests/test_api.py
```

Kết quả đúng: `25 dat, 0 loi`. Test có sửa trực tiếp database (giả lập OTP hết hạn), nên cần chạy cùng máy với server. Muốn chạy lại từ đầu thì dừng server, chạy lại `database/init_db.py` rồi khởi động server.

## Danh sách API

| Method | URI | Mô tả | Status |
|---|---|---|---|
| GET | /api/users | Danh sách người dùng | 200 |
| GET | /api/users/{id} | Chi tiết người dùng | 200, 404 |
| GET | /api/wallets | Danh sách ví kèm số dư | 200 |
| GET | /api/wallets/{id} | Chi tiết ví | 200, 404 |
| GET | /api/transactions | Danh sách giao dịch | 200 |
| GET | /api/transactions/{id} | Chi tiết giao dịch | 200, 404 |
| GET | /api/ledger | Sổ cái biến động số dư | 200 |
| POST | /api/transfers | Tạo giao dịch chuyển tiền, sinh OTP | 201, 400, 404 |
| POST | /api/transfers/{id}/confirm | Xác thực OTP và thực hiện chuyển tiền | 200, 400, 404, 409, 410 |

Request tạo giao dịch:

```json
{"sender_wallet_id": 1, "receiver_wallet_id": 2, "amount": 50000}
```

Request xác thực OTP:

```json
{"code": "123456"}
```

Đường dẫn không tồn tại trả 404, đúng đường dẫn nhưng sai method trả 405, body không phải JSON hợp lệ trả 400.

## Thiết kế chính

- Database: 5 bảng `users`, `wallets`, `transactions`, `otp_codes`, `ledger` với khóa chính, khóa ngoại, UNIQUE và CHECK. Tiền lưu bằng số nguyên (VND).
- OTP: 6 chữ số, gắn với một giao dịch, hiệu lực 5 phút, chỉ dùng được một lần. Email giả lập bằng cách in ra console của server.
- Transaction: bước xác nhận chạy trong một transaction SQL (`BEGIN IMMEDIATE`), nếu lỗi giữa chừng thì `ROLLBACK`. Trừ tiền, cộng tiền, ghi 2 dòng Ledger (DEBIT/CREDIT), đánh dấu OTP đã dùng và đổi trạng thái giao dịch xảy ra cùng nhau hoặc không xảy ra.
- Response tạo giao dịch có trường `demo_otp` chỉ để tiện test, cần bỏ khi triển khai thật.

## Lộ trình

1. Python thuần: API, database, trang admin (đang làm)
2. Đăng nhập, lịch sử giao dịch, giao diện người dùng, test concurrency
3. Các bước sau theo yêu cầu của môn học
