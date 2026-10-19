# P2P Wallet Pro - Hệ Thống Ví Điện Tử Bán Tự Động (SOA / Microservices)

**P2P Wallet Pro** là hệ thống ví điện tử phân tán được thiết kế theo kiến trúc **Hướng dịch vụ (SOA / Microservices Architecture)** bằng ngôn ngữ Python thuần, phục vụ báo cáo đồ án. 

Hệ thống cho phép người dùng đăng ký, đăng nhập bảo mật, tra cứu số dư, thực hiện giao dịch chuyển tiền P2P bán tự động qua xác thực mã OTP 2FA và ghi nhận lịch sử biến động số dư theo chuẩn **Sổ cái kép (Ledger)**.

---

## 1. Kiến Trúc Hệ Thống (Microservices Architecture)

Hệ thống được bóc tách hoàn toàn thành **4 Microservices độc lập**, chạy trên 4 cổng (Ports) riêng biệt và giao tiếp thông qua chuẩn **RESTful API (JSON over HTTP)**:

```text
                       ┌─────────────────────────────────────────┐
                       │          Trình Duyệt (Web Client)       │
                       └────────────────────┬────────────────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────────────┐
        │ Port 8001                         │ Port 8002                         │ Port 8000
        ▼                                   ▼                                   ▼
┌───────────────┐                   ┌───────────────┐                   ┌───────────────┐
│ User Service  │                   │ Wallet Service│                   │Transfer Serv. │
│ (Auth & Users)│                   │(Ledger & Bal.)│                   │(Orchestrator) │
└───────────────┘                   └───────────────┘                   └───────┬───────┘
                                                                                │
                                            │ Port 8003                         │
                                            ▼                                   │
                                    ┌───────────────┐                           │
                                    │ Notification  │◀──────────────────────────┘
                                    │ Service (OTP) │
                                    └───────────────┘
```

| Microservice | Port | Database | Trách nhiệm chính (Single Responsibility) |
| :--- | :---: | :--- | :--- |
| **`User Service`** | `8001` | `p2p_wallet.db` | Quản lý tài khoản, Đăng ký, Đăng nhập (Mã hóa SHA-256). |
| **`Wallet Service`** | `8002` | `p2p_wallet.db` | Tra cứu số dư ví, thực thi trừ/cộng tiền an toàn, ghi Sổ cái (`LEDGER`). |
| **`Notification Service`** | `8003` | `p2p_wallet.db` | Khởi tạo mã OTP ngẫu nhiên (hạn 5 phút), kiểm tra & xác thực OTP. |
| **`Transfer Service`** | `8000` | `p2p_wallet.db` | **Orchestrator**: Điều phối luồng chuyển tiền, phục vụ Static Web UI & Admin Panel. |

---

## 2. Tính Năng Nổi Bật

1. **Quản lý Tài khoản & Bảo mật (User & Auth):**
   * Đăng ký tài khoản mới $\rightarrow$ Tự động tạo ví chính và tặng kèm **1,000,000 VND** trải nghiệm.
   * Mật khẩu được mã hóa băm bằng thuật toán **SHA-256**.
2. **Giao dịch P2P & Xác thực 2FA OTP:**
   * Tra cứu thông tin người nhận theo ID ví theo thời gian thực (Real-time Lookup).
   * Quy trình chuyển tiền bán tự động 2 bước: `Khởi tạo (PENDING)` $\rightarrow$ `Nhập OTP` $\rightarrow$ `Hoàn tất (SUCCESS)`.
   * Mã OTP tự động hết hạn sau 5 phút và tự vô hiệu hóa sau khi sử dụng (`is_used`).
3. **Cơ chế Sổ Cái (Ledger) & Chống Âm Tiền (Concurrency Control):**
   * Mỗi giao dịch `SUCCESS` sinh ra đúng 2 bút toán đối ứng: `DEBIT` (Trừ người gửi) và `CREDIT` (Cộng người nhận).
   * Sử dụng cơ chế khóa `BEGIN IMMEDIATE` trong SQLite chống lỗi đua điều kiện (Race Condition) và đảm bảo số dư không bị âm.
4. **Giao diện Web Frontend Fintech:**
   * Giao diện hiện đại sử dụng Bootstrap 5, Toast Notification kèm thanh đếm ngược thời gian tuột dần.
   * Trang **Admin Panel (`/admin`)** theo dõi toàn bộ dữ liệu real-time từ cả 4 cổng Microservices.

---

## 3. Cấu Trúc Thư Mục Dự Án

```text
p2p-wallet/
├── data/
│   └── p2p_wallet.db            # Database SQLite chính
├── database/
│   ├── init_db.py               # Script khởi tạo cơ sở dữ liệu ban đầu
│   └── schema.sql               # Định nghĩa cấu trúc các bảng SQL
├── docs/
│   ├── diagrams/                # Sơ đồ ERD & Use Case
│   └── report/                  # Báo cáo đồ án
├── frontend/
│   ├── index.html               # Giao diện chính người dùng (Client Web)
│   ├── admin.html               # Trang quản trị Admin (Monitoring Panel)
│   ├── style.css                # CSS tùy biến & OTP Modal
│   └── app.js                   # Logic JavaScript gọi API phân tán 4 Ports
├── services/
│   ├── user_service.py          # Microservice Quản lý User (Port 8001)
│   ├── wallet_service.py        # Microservice Quản lý Ví & Sổ cái (Port 8002)
│   ├── notification_service.py  # Microservice Tạo & Xác thực OTP (Port 8003)
│   └── transfer_service.py      # Microservice Điều phối Giao dịch (Port 8000)
├── run_all.py                   # Script khởi chạy đồng thời 4 Microservices
├── README.md                    # Tài liệu hướng dẫn dự án
└── .gitignore
```

---

## 4. Mô Hình Cơ Sở Dữ Liệu (Database Schema)

Cơ sở dữ liệu gồm 5 bảng chính được thiết kế chuẩn hóa:

* **`USERS`**: `id` (PK), `username`, `email`, `password_hash`, `created_at`
* **`WALLETS`**: `id` (PK), `user_id` (FK), `balance`, `currency`
* **`TRANSACTIONS`**: `id` (PK), `sender_wallet_id` (FK), `receiver_wallet_id` (FK), `amount`, `status` (`PENDING`/`SUCCESS`/`FAILED`), `created_at`
* **`OTP_CODES`**: `id` (PK), `transaction_id` (FK), `code`, `expires_at`, `is_used`
* **`LEDGER`**: `id` (PK), `wallet_id` (FK), `transaction_id` (FK), `type` (`DEBIT`/`CREDIT`), `amount`, `balance_after`, `created_at`

---

## 5. Hướng Dẫn Cài Đặt & Khởi Chạy

### Yêu cầu hệ thống:
* Python 3.8 trở lên.
* Trình duyệt Web (Chrome, Edge, Firefox).

### Các bước khởi chạy:

1. **Khởi tạo cơ sở dữ liệu mẫu (Nếu chưa có file DB):**
   ```bash
   python database/init_db.py
   ```

2. **Khởi chạy toàn bộ 4 Microservices:**
   Chạy duy nhất 1 câu lệnh tại thư mục gốc của dự án:
   ```bash
   python run_all.py
   ```

3. **Truy cập ứng dụng:**
   * **Giao diện Người dùng chính:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
   * **Trang Quản trị Admin Panel:** [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)

---

## 6. Danh Sách RESTful API Endpoints

### 🔹 User Service (`http://127.0.0.1:8001`)
* `GET /` : Trang kiểm tra trạng thái Service Health Check.
* `GET /api/users` : Lấy danh sách tất cả người dùng.
* `POST /api/register` : Đăng ký tài khoản mới (Tự động tạo ví & tặng 1M VND).
* `POST /api/login` : Đăng nhập & xác thực mật khẩu.

### 🔹 Wallet Service (`http://127.0.0.1:8002`)
* `GET /` : Trang kiểm tra trạng thái Service Health Check.
* `GET /api/wallets` : Lấy danh sách tất cả các ví.
* `GET /api/wallets/:id` : Tra cứu chi tiết ví theo ID.
* `GET /api/ledger` : Lấy toàn bộ sổ cái biến động số dư.
* `POST /api/wallets/transfer-execute` : Thực thi trừ/cộng số dư và ghi Sổ cái.

### 🔹 Notification Service (`http://127.0.0.1:8003`)
* `GET /` : Trang kiểm tra trạng thái Service Health Check.
* `POST /api/otp/generate` : Khởi tạo mã OTP 6 số cho giao dịch.
* `POST /api/otp/verify` : Xác thực mã OTP người dùng nhập.

### 🔹 Transfer Service (`http://127.0.0.1:8000`)
* `GET /` : Trả về trang Web Client `index.html`.
* `GET /admin` : Trả về trang Dashboard `admin.html`.
* `GET /api/transactions` : Lấy danh sách tất cả giao dịch P2P.
* `POST /api/transfers` : Khởi tạo lệnh chuyển tiền P2P (`PENDING`).
* `POST /api/transfers/:id/confirm` : Xác nhận mã OTP và hoàn tất giao dịch.

---

## 7. Kịch Bản Trình Diễn Báo Cáo Vấn Đáp (Demo Scenario)

Khi trình bày trước Hội đồng / Giảng viên:

1. **Kiểm tra tính độc lập (4 Ports):** Mở 4 URL `http://127.0.0.1:8001/`, `:8002/`, `:8003/`, `:8000/` để chứng minh 4 Microservices đang chạy độc lập trên các tiến trình riêng biệt.
2. **Thao tác nghiệp vụ:** Đăng ký tài khoản mới $\rightarrow$ Đăng nhập $\rightarrow$ Chuyển tiền sang Ví #2 $\rightarrow$ Nhập OTP $\rightarrow$ Nhận Toast thông báo thành công.
3. **Kiểm tra Sổ cái Ledger:** Mở trang Admin `http://127.0.0.1:8000/admin` để cho giảng viên thấy 2 dòng đối ứng `DEBIT` và `CREDIT` được ghi nhận chính xác trong Sổ cái.
4. **Thử nghiệm tính chịu lỗi (Fault Tolerance):**
   * Tắt tiến trình `User Service (8001)` $\rightarrow$ Chức năng Đăng nhập bị ngừng, nhưng hệ thống không bị crash toàn bộ.
   * Tắt `Notification Service (8003)` $\rightarrow$ Tạo giao dịch báo lỗi dừng ở bước sinh OTP, chứng minh không bị ảnh hưởng chéo (Isolation).