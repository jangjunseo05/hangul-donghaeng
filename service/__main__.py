"""Start the local broker without printing credentials."""
from pathlib import Path
import os
import secrets

from dotenv import load_dotenv, set_key
import uvicorn

root = Path(__file__).resolve().parents[1]
config = root / ".env"
if not config.exists():
    config.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
load_dotenv(config)
if not os.getenv("WORKER_TOKEN"):
    worker_token = secrets.token_urlsafe(32)
    set_key(str(config), "WORKER_TOKEN", worker_token)
    os.environ["WORKER_TOKEN"] = worker_token

if __name__ == "__main__":
    uvicorn.run("service.main:app", host=os.getenv("GUIDE_BIND", "127.0.0.1"),
                port=int(os.getenv("GUIDE_PORT", "8000")), log_level="info")
