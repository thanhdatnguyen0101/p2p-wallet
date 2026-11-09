import os
import subprocess
import sys
import time

if sys.platform == "win32":
  try:
    sys.stdout.reconfigure(encoding="utf-8")
  except Exception:
    pass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

services = [
    ("User Service", [sys.executable, "-m", "services.user_service"]),
    ("Wallet Service", [sys.executable, "-m", "services.wallet_service"]),
    ("Notification Service", [sys.executable, "-m", "services.notification_service"]),
    ("Transfer Service", [sys.executable, "-m", "services.transfer_service"]),
]

processes = []

print("P2P Wallet Microservices (FastAPI)...\n")

try:
  for name, cmd in services:
    p = subprocess.Popen(cmd, cwd=ROOT_DIR)
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
