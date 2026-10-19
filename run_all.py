import os
import subprocess
import sys
import time
if sys.platform == "win32":
  try:
    sys.stdout.reconfigure(encoding="utf-8")
  except Exception:
    pass
services = [
    "services/user_service.py",
    "services/wallet_service.py",
    "services/notification_service.py",
    "services/transfer_service.py",
]

processes = []

print("P2P Wallet Microservices...\n")

try:
  for service in services:
    p = subprocess.Popen([sys.executable, service])
    processes.append(p)
    time.sleep(0.5)

  print(
      "\nTất cả 4 Microservices đã chạy thành công! Mở"
      " http://127.0.0.1:8000 trên trình duyệt."
  )

  # Giữ script chạy
  for p in processes:
    p.wait()

except KeyboardInterrupt:
  print("\nĐang dừng tất cả Microservices...")
  for p in processes:
    p.terminate()
  print("Đã tắt toàn bộ hệ thống!")