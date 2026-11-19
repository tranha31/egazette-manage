"""Cấu hình đọc từ biến môi trường / file .env (xem .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
# File .env ở thư mục gốc dự án (cạnh docker-compose.yml) chứa key MinIO dùng chung với docker compose; không ghi đè giá trị đã có
load_dotenv(ROOT.parent / ".env")


def _bool(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- database (MySQL). Mặc định trỏ vào container trong docker-compose.yml (cổng 3307)
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://egazette:egazette@127.0.0.1:3307/egazette?charset=utf8mb4",
    )
    AUTO_CREATE_TABLES = _bool("AUTO_CREATE_TABLES", True)

    # --- lưu file PDF trên MinIO (S3). Database chỉ lưu bucket + object key (xem app/storage.py)
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")      # host:port, KHÔNG kèm http://
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "egazette")
    MINIO_SECURE = _bool("MINIO_SECURE", False)                          # true nếu MinIO chạy HTTPS
    MINIO_REGION = os.getenv("MINIO_REGION", "") or None
    # Thư mục PDF cũ trên đĩa (bản trước khi dùng MinIO): chỉ dùng làm nguồn cho `python -m app.migrate_pdfs`
    LEGACY_STORAGE_DIR = Path(os.getenv("LEGACY_STORAGE_DIR") or os.getenv("STORAGE_DIR") or "storage")
    if not LEGACY_STORAGE_DIR.is_absolute():
        LEGACY_STORAGE_DIR = ROOT / LEGACY_STORAGE_DIR           # đường dẫn tương đối tính từ thư mục backend

    # --- web
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8000"))
    SECRET_KEY = os.getenv("SECRET_KEY", "doi-chuoi-nay-trong-file-.env")
    # Nếu đặt cả hai thì mọi trang yêu cầu đăng nhập (HTTP Basic). Nên đặt khi mở cho nhiều người dùng.
    APP_USER = os.getenv("APP_USER", "")
    APP_PASSWORD = os.getenv("APP_PASSWORD", "")
    PER_PAGE = int(os.getenv("PER_PAGE", "25"))
    # true khi backend đứng sau reverse proxy (nginx trong docker-compose): tin header X-Forwarded-For/-Proto để biết IP thật.
    # Đừng bật khi backend nhận kết nối trực tiếp từ người dùng (header có thể bị giả).
    TRUST_PROXY = _bool("TRUST_PROXY", False)
    # Frontend tách riêng (React). Hai cách chạy:
    #  1. Cùng một địa chỉ: `npm run build` trong ../frontend rồi backend tự phục vụ thư mục dist (FRONTEND_DIST).
    #  2. Khác địa chỉ (vd frontend ở https://app.example.com): đặt CORS_ORIGINS=https://app.example.com
    FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST") or ROOT.parent / "frontend" / "dist")
    CORS_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    # --- thời gian
    APP_TZ = os.getenv("APP_TZ", "Asia/Ho_Chi_Minh")
    # Ngày hôm nay chưa kết thúc nên chưa chắc đã có đủ bố cáo. Nếu vừa crawl trong vòng N phút
    # thì coi như "hôm nay" cũng đã được phủ, không crawl lại (xem app/coverage.py).
    TODAY_RECHECK_MINUTES = int(os.getenv("TODAY_RECHECK_MINUTES", "60"))

    # --- crawler / 2captcha
    CRAWLER = os.getenv("CRAWLER", "playwright")  # playwright | (test dùng crawler giả)
    HEADLESS = _bool("HEADLESS", False)
    APIKEY_2CAPTCHA = os.getenv("APIKEY_2CAPTCHA", "")
    API_KEY_FILE = Path(os.getenv("API_KEY_FILE", str(ROOT / "api_key.txt")))
    MIN_BALANCE = float(os.getenv("MIN_BALANCE", "0.01"))
    START_WORKER = _bool("START_WORKER", True)

    @classmethod
    def api_key(cls):
        if cls.APIKEY_2CAPTCHA:
            return cls.APIKEY_2CAPTCHA
        if cls.API_KEY_FILE.exists():
            key = cls.API_KEY_FILE.read_text(encoding="utf-8-sig").strip()
            if key and not key.startswith("DÁN"):
                return key
        return ""
