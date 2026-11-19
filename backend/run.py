"""Chạy backend (REST API):  python run.py   (mặc định http://127.0.0.1:8000, API ở /api)

Nếu frontend đã build (../frontend/dist) thì backend phục vụ luôn giao diện React ở cùng địa chỉ."""
import sys

from app.config import Config
from app.crawler import make_crawler
from app.storage import StoreError, get_store
from app.web import create_app
from app.worker import Worker


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    worker = Worker(make_crawler) if Config.START_WORKER else None
    try:
        app = create_app(worker)       # khởi tạo database + bảng
    except Exception as e:  # noqa: BLE001
        host = Config.DATABASE_URL.split("@")[-1]
        sys.exit(f"Không kết nối được database ({host}): {e.__class__.__name__}: {str(e)[:200]}\n"
                 "-> Chạy MySQL đi kèm bằng:  docker compose --profile mysql up -d mysql   (đợi ~30 giây)\n"
                 "-> hoặc sửa DATABASE_URL trong file .env trỏ tới MySQL của bạn.")
    try:
        get_store().ensure_bucket()    # tạo bucket nếu chưa có
        print(f"MinIO: {Config.MINIO_ENDPOINT} · bucket '{Config.MINIO_BUCKET}' sẵn sàng", flush=True)
    except StoreError as e:
        print(f"(!) MinIO chưa dùng được: {e}\n    Xem/tìm kiếm dữ liệu vẫn được, nhưng crawl sẽ tạm dừng và không xem được PDF. "
              "Chạy MinIO bằng:  docker compose up -d minio  (key trong .env cạnh docker-compose.yml)", flush=True)
    if worker:
        worker.start()                 # worker nền xử lý hàng đợi crawl
    from waitress import serve
    print(f"Egazette API chạy tại http://{Config.HOST}:{Config.PORT}/api  (Ctrl+C để dừng)", flush=True)
    if (Config.FRONTEND_DIST / "index.html").is_file():
        print(f"Giao diện: http://{Config.HOST}:{Config.PORT}/", flush=True)
    elif not Config.TRUST_PROXY:      # trong docker-compose giao diện do nginx phục vụ, không cần nhắc
        print("Chưa có bản build giao diện. Dev: cd ../frontend && npm run dev (http://localhost:5173) "
              "· hoặc npm run build rồi chạy lại.", flush=True)
    if not Config.api_key():
        print("(!) Chưa có API key 2captcha: xem/tìm kiếm dữ liệu được, nhưng crawl sẽ tạm dừng. "
              "Đặt APIKEY_2CAPTCHA trong .env hoặc tạo file api_key.txt", flush=True)
    try:
        serve(app, host=Config.HOST, port=Config.PORT, threads=8)
    finally:
        if worker:
            worker.stop()


if __name__ == "__main__":
    main()
