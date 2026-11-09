"""Package runner for Transfer Service."""
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .main import app, PORT
import uvicorn

if __name__ == "__main__":
    print(f"[Transfer Orchestrator] đang chạy tại http://127.0.0.1:{PORT}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT)
