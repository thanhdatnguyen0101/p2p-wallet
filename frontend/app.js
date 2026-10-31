// Cấu hình Port độc lập cho từng Microservice
const USER_SERVICE = "http://127.0.0.1:8001";
const WALLET_SERVICE = "http://127.0.0.1:8002";
const NOTIFICATION_SERVICE = "http://127.0.0.1:8003";
const TRANSFER_SERVICE = "http://127.0.0.1:8000";

let currentUserId = null;
let currentUserWalletId = null;
let activeTransactionId = null;
let otpCountdownTimer = null; // Biến quản lý bộ đếm ngược OTP

async function apiCall(baseUrl, path, method = "GET", body = null) {
    const options = { method, headers: { "Content-Type": "application/json" } };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(baseUrl + path, options);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || "Có lỗi xảy ra");
    return data;
}

// 1. Đăng Nhập (USER_SERVICE 8001)
async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById("loginUser").value.trim();
    const password = document.getElementById("loginPass").value.trim();
    document.getElementById("loginError").textContent = "";

    try {
        const res = await apiCall(USER_SERVICE, "/api/login", "POST", { username, password });

        if (res.user.is_admin) {
            sessionStorage.setItem("p2p_admin_session", JSON.stringify({ username: res.user.username }));
            window.location.href = "/admin";
            return;
        }

        currentUserId = res.user.id;
        document.getElementById("navUsername").textContent = res.user.username;
        document.getElementById("profileName").textContent = res.user.username;

        document.getElementById("loginView").classList.add("d-none");
        document.getElementById("dashboardView").classList.remove("d-none");
        document.getElementById("userInfo").classList.replace("d-none", "d-flex");

        showToast(`Chào mừng ${res.user.username} quay trở lại!`, "success", 3000);
        await loadDashboardData();
    } catch (err) {
        document.getElementById("loginError").textContent = err.message;
    }
}

// 2. Đăng Ký (USER_SERVICE 8001)
async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById("regUser").value.trim();
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPass").value.trim();
    document.getElementById("regError").textContent = "";

    try {
        await apiCall(USER_SERVICE, "/api/register", "POST", { username, email, password });
        
        showToast("Đăng ký tài khoản thành công! Tặng ngay 1,000,000 VND vào ví.", "success", 4000);
        document.getElementById("registerForm").reset();

        switchTab('login');
        document.getElementById("loginUser").value = username;
    } catch (err) {
        document.getElementById("regError").textContent = err.message;
    }
}

// 3. Tra cứu Ví (WALLET_SERVICE 8002)
async function lookupReceiver() {
    const rid = document.getElementById("receiverWalletId").value;
    const infoDiv = document.getElementById("receiverInfo");
    infoDiv.textContent = "";
    if (!rid) return;
    try {
        const wallet = await apiCall(WALLET_SERVICE, `/api/wallets/${rid}`);
        infoDiv.textContent = `✓ Người nhận: ${wallet.username} (Ví #${wallet.id})`;
        infoDiv.className = "form-text mt-1 text-success fw-semibold";
    } catch (err) {
        infoDiv.textContent = "❌ Không tìm thấy ví (Wallet Service 8002)";
        infoDiv.className = "form-text mt-1 text-danger fw-semibold";
    }
}

// 4. Tải Số Dư & Lịch Sử (WALLET_SERVICE 8002 & TRANSFER_SERVICE 8000)
async function loadDashboardData() {
    if (!currentUserId) return;
    try {
        const wallets = await apiCall(WALLET_SERVICE, "/api/wallets");
        const myWallet = wallets.find(w => w.user_id === currentUserId);
        if (myWallet) {
            currentUserWalletId = myWallet.id;
            document.getElementById("userBalance").textContent = Number(myWallet.balance).toLocaleString("vi-VN") + " " + myWallet.currency;
            document.getElementById("profileWalletId").textContent = "#" + myWallet.id;
        } else {
            currentUserWalletId = null;
            document.getElementById("userBalance").textContent = "0 VND";
            document.getElementById("profileWalletId").textContent = "#--";
        }

        const txs = await apiCall(TRANSFER_SERVICE, "/api/transactions");
        const myTxs = txs.filter(t => t.sender_wallet_id === currentUserWalletId || t.receiver_wallet_id === currentUserWalletId).reverse();

        const tbody = document.getElementById("transactionHistoryTable");
        tbody.innerHTML = myTxs.length ? "" : '<tr><td colspan="5" class="text-center py-3 text-muted">Chưa có giao dịch nào</td></tr>';

        myTxs.forEach(t => {
            const isSender = t.sender_wallet_id === currentUserWalletId;
            const typeBadge = isSender 
                ? '<span class="text-danger fw-bold"><i class="bi bi-arrow-up-right-circle"></i> Chuyển đi</span>' 
                : '<span class="text-success fw-bold"><i class="bi bi-arrow-down-left-circle"></i> Nhận tiền</span>';
            
            // Truyền t.created_at vào showOtpModal để tính toán thời hạn OTP còn lại
            const statusBadge = t.status === 'SUCCESS' ? '<span class="badge-status badge-success">Thành công</span>'
                : t.status === 'PENDING' ? `
                    <span class="badge-status badge-pending">Chờ OTP</span>
                    <button class="btn btn-sm btn-warning py-0 px-2 ms-1 fw-bold" onclick="showOtpModal(${t.id}, '${t.created_at}')">
                        <i class="bi bi-key"></i> Nhập OTP
                    </button>
                `
                : '<span class="badge-status badge-failed">Thất bại</span>';

            tbody.innerHTML += `
                <tr>
                    <td><strong>#${t.id}</strong></td>
                    <td>${typeBadge}</td>
                    <td class="${isSender ? 'text-danger' : 'text-success'} fw-bold">
                        ${isSender ? '-' : '+'}${Number(t.amount).toLocaleString("vi-VN")} VND
                    </td>
                    <td>${statusBadge}</td>
                    <td class="small text-muted">${t.created_at}</td>
                </tr>
            `;
        });
    } catch (err) {
        console.error("Lỗi tải dashboard:", err);
    }
}

// 5. Tạo chuyển tiền (TRANSFER_SERVICE 8000)
async function initiateTransfer(e) {
    e.preventDefault();
    document.getElementById("transferError").textContent = "";
    const receiverId = parseInt(document.getElementById("receiverWalletId").value);
    const amount = parseInt(document.getElementById("transferAmount").value);

    try {
        const res = await apiCall(TRANSFER_SERVICE, "/api/transfers", "POST", {
            sender_wallet_id: currentUserWalletId,
            receiver_wallet_id: receiverId,
            amount: amount
        });

        // Giao dịch mới khởi tạo -> Bật modal tính đếm ngược ngay
        showOtpModal(res.transaction_id, new Date().toISOString().replace('T', ' ').substring(0, 19));
        await loadDashboardData();
    } catch (err) {
        document.getElementById("transferError").textContent = err.message;
    }
}

// 6. Xác nhận OTP (TRANSFER_SERVICE 8000)
async function confirmOTP() {
    const digits = Array.from(document.querySelectorAll('.otp-digit')).map(i => i.value).join('');
    document.getElementById("otpError").textContent = "";

    if (digits.length < 6) {
        document.getElementById("otpError").textContent = "Vui lòng nhập đủ 6 chữ số OTP";
        return;
    }

    try {
        await apiCall(TRANSFER_SERVICE, `/api/transfers/${activeTransactionId}/confirm`, "POST", { code: digits });
        
        closeOtpModal();
        showToast("Giao dịch thanh toán thành công!", "success", 3500);
        document.getElementById("transferForm").reset();
        document.getElementById("receiverInfo").textContent = "";
        await loadDashboardData();
    } catch (err) {
        document.getElementById("otpError").textContent = err.message;
    }
}

// --- QUẢN LÝ BỘ ĐẾM NGƯỢC THỜI GIAN THEO THỰC TẾ ---
function startOtpTimer(remainingSeconds) {
    clearInterval(otpCountdownTimer);
    let remaining = remainingSeconds;
    const timerDisplay = document.getElementById("otpTimer");
    const errEl = document.getElementById("otpError");

    function update() {
        if (remaining <= 0) {
            clearInterval(otpCountdownTimer);
            if (timerDisplay) timerDisplay.textContent = "00:00";
            if (errEl) errEl.textContent = "Mã OTP đã hết hạn!";
            document.querySelectorAll('.otp-digit').forEach(i => i.disabled = true);
            return;
        }

        const minutes = String(Math.floor(remaining / 60)).padStart(2, '0');
        const seconds = String(remaining % 60).padStart(2, '0');
        if (timerDisplay) {
            timerDisplay.textContent = `${minutes}:${seconds}`;
        }
        remaining--;
    }

    update();
    if (remaining > 0) {
        otpCountdownTimer = setInterval(update, 1000);
    }
}

// Show Modal OTP & Tính toán thời gian thực tế còn lại
function showOtpModal(txId, createdAtStr = null) {
    activeTransactionId = txId;

    // Reset giao diện ô nhập
    document.querySelectorAll('.otp-digit').forEach(i => {
        i.value = '';
        i.disabled = false;
    });
    const errEl = document.getElementById("otpError");
    if (errEl) errEl.textContent = "";

    // Tính thời gian còn lại (tối đa 300s / 5 phút)
    let remainingSeconds = 300;
    if (createdAtStr) {
        // Chuyển chuỗi YYYY-MM-DD HH:MM:SS (UTC) sang timestamp
        const txTime = new Date(createdAtStr.replace(" ", "T")).getTime();        
        const now = Date.now();
        const elapsedSeconds = Math.floor((now - txTime) / 1000);
        remainingSeconds = 300 - elapsedSeconds;
    }

    // Khởi động bộ đếm với thời gian thực còn lại
    startOtpTimer(remainingSeconds);

    const modalEl = document.getElementById('otpModal');
    if (modalEl) {
        modalEl.classList.add('show');
        modalEl.style.display = 'block';
        modalEl.removeAttribute('aria-hidden');

        if (!document.querySelector('.modal-backdrop')) {
            const backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade show';
            document.body.appendChild(backdrop);
        }
    }
}

// Close Modal OTP & Dừng bộ đếm
function closeOtpModal() {
    clearInterval(otpCountdownTimer);

    const modalEl = document.getElementById('otpModal');
    if (modalEl) {
        modalEl.classList.remove('show');
        modalEl.style.display = 'none';
        modalEl.setAttribute('aria-hidden', 'true');

        const backdrop = document.querySelector('.modal-backdrop');
        if (backdrop) backdrop.remove();
    }
}

function logout() {
    clearInterval(otpCountdownTimer);
    currentUserId = null;
    currentUserWalletId = null;
    document.getElementById("dashboardView").classList.add("d-none");
    document.getElementById("loginView").classList.remove("d-none");
    document.getElementById("userInfo").classList.replace("d-flex", "d-none");

    document.getElementById("userBalance").textContent = "0 VND";
    document.getElementById("profileWalletId").textContent = "#--";
    document.getElementById("profileName").textContent = "--";
    document.getElementById("loginForm").reset();
}

function switchTab(type) {
    const loginTab = document.getElementById('login-tab');
    const registerTab = document.getElementById('register-tab');
    const loginPanel = document.getElementById('login-panel');
    const registerPanel = document.getElementById('register-panel');

    if (!loginTab || !registerTab || !loginPanel || !registerPanel) return;

    if (type === 'register') {
        loginTab.classList.remove('active');
        registerTab.classList.add('active');
        loginPanel.classList.remove('show', 'active');
        registerPanel.classList.add('show', 'active');
    } else {
        registerTab.classList.remove('active');
        loginTab.classList.add('active');
        registerPanel.classList.remove('show', 'active');
        if (loginPanel.classList.show) loginPanel.classList.add('show', 'active');
    }
}

function showToast(message, type = 'success', duration = 3500) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '1090';
        document.body.appendChild(container);
    }

    const iconMap = {
        success: 'bi-check-circle-fill text-success',
        danger: 'bi-x-circle-fill text-danger',
        warning: 'bi-exclamation-triangle-fill text-warning'
    };

    const toast = document.createElement('div');
    toast.className = `custom-toast toast-${type} p-3 d-flex align-items-center justify-content-between`;
    
    toast.innerHTML = `
        <div class="d-flex align-items-center gap-2">
            <i class="bi ${iconMap[type] || iconMap.success} fs-5"></i>
            <span class="fw-semibold text-dark small">${message}</span>
        </div>
        <button type="button" class="btn-close ms-2 btn-close-sm" onclick="this.parentElement.remove()"></button>
        <div class="toast-progress">
            <div class="toast-progress-bar" style="width: 100%; transition: width ${duration}ms linear;"></div>
        </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        const progressBar = toast.querySelector('.toast-progress-bar');
        if (progressBar) progressBar.style.width = '0%';
    }, 20);

    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Bổ sung gán hàm toàn cục cho window
window.switchTab = switchTab;
window.showOtpModal = showOtpModal;
window.closeOtpModal = closeOtpModal;
window.handleLogin = handleLogin;
window.handleRegister = handleRegister;
window.logout = logout;
window.lookupReceiver = lookupReceiver;
window.initiateTransfer = initiateTransfer;
window.confirmOTP = confirmOTP;
window.loadDashboardData = loadDashboardData;

// Tự động chuyển focus giữa 6 ô OTP
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('.otp-digit').forEach((input, index, inputs) => {
        input.addEventListener('keyup', (e) => {
            if (e.key >= '0' && e.key <= '9') {
                if (index < inputs.length - 1) inputs[index + 1].focus();
            } else if (e.key === 'Backspace') {
                if (index > 0) inputs[index - 1].focus();
            }
        });
    });
});