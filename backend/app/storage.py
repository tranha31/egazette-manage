"""Kho lưu file PDF trên MinIO (tương thích S3).

Database lưu `pdf_bucket` + `pdf_path` (= object key); file thật nằm trên MinIO. Backend không giữ PDF trên đĩa:
crawl xong thì tải về thư mục tạm, tách nội dung, upload lên MinIO rồi xoá file tạm.

`MinioStore` là bản thật; `MemoryStore` giữ file trong bộ nhớ, dùng cho test.
"""
import threading
from pathlib import Path

from .config import Config

PDF_TYPE = "application/pdf"


class StoreError(Exception):
    """Không nói chuyện được với MinIO (mất kết nối, sai key, bucket không tồn tại, ...)."""


class PdfStore:
    bucket: str

    def ensure_bucket(self):
        raise NotImplementedError

    def stat(self, key, bucket=None):
        """Kích thước (byte) của object, hoặc None nếu không có."""
        raise NotImplementedError

    def put_file(self, key, path, bucket=None):
        """Upload file cục bộ lên key; trả về kích thước."""
        raise NotImplementedError

    def open(self, key, bucket=None):
        """(kích thước, iterator các khối byte) để stream ra HTTP. Lỗi kết nối nổi lên ngay, trước khi stream."""
        raise NotImplementedError

    def download(self, key, dest, bucket=None):
        raise NotImplementedError

    def remove(self, key, bucket=None):
        raise NotImplementedError

    def exists(self, key, bucket=None):
        size = self.stat(key, bucket)
        return size is not None and size > 0


# ------------------------------------------------------------------ MinIO thật
class MinioStore(PdfStore):
    def __init__(self, endpoint, access_key, secret_key, bucket, secure=False, region=None):
        import urllib3
        from minio import Minio
        # Timeout ngắn + ít lần thử lại để MinIO tắt thì báo lỗi nhanh thay vì treo cả worker / request
        http = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=5, read=60),
            retries=urllib3.Retry(total=2, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504)),
            maxsize=10)
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure, region=region,
                            http_client=http)
        self.bucket = bucket
        self.endpoint = endpoint

    @staticmethod
    def _wrap(e):
        return StoreError(f"MinIO: {e.__class__.__name__}: {str(e)[:300]}")

    def _call(self, fn, *a, **kw):
        from minio.error import MinioException
        from urllib3.exceptions import HTTPError
        try:
            return fn(*a, **kw)
        except (MinioException, HTTPError, OSError) as e:
            raise self._wrap(e) from e

    def ensure_bucket(self):
        if not self._call(self.client.bucket_exists, self.bucket):
            self._call(self.client.make_bucket, self.bucket)

    def stat(self, key, bucket=None):
        from minio.error import S3Error
        try:
            return self._call(self.client.stat_object, bucket or self.bucket, key).size
        except StoreError as e:
            if isinstance(e.__cause__, S3Error) and e.__cause__.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
                return None
            raise

    def put_file(self, key, path, bucket=None):
        self._call(self.client.fput_object, bucket or self.bucket, key, str(path), content_type=PDF_TYPE)
        return Path(path).stat().st_size

    def open(self, key, bucket=None):
        b = bucket or self.bucket
        size = self.stat(key, b)
        if size is None:
            raise FileNotFoundError(key)
        resp = self._call(self.client.get_object, b, key)

        def chunks():
            try:
                yield from resp.stream(64 * 1024)
            finally:
                resp.close()
                resp.release_conn()
        return size, chunks()

    def download(self, key, dest, bucket=None):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        self._call(self.client.fget_object, bucket or self.bucket, key, str(dest))

    def remove(self, key, bucket=None):
        self._call(self.client.remove_object, bucket or self.bucket, key)


# ------------------------------------------------------------------ bản giả cho test
class MemoryStore(PdfStore):
    def __init__(self, bucket="egazette-test"):
        self.bucket = bucket
        self.objects = {}
        self.fail = None           # đặt thành chuỗi để giả lập MinIO mất kết nối
        self.fail_on_put = None    # chỉ lỗi khi upload
        self.buckets = set()

    def _check(self):
        if self.fail:
            raise StoreError(self.fail)

    def ensure_bucket(self):
        self._check()
        self.buckets.add(self.bucket)

    def stat(self, key, bucket=None):
        self._check()
        data = self.objects.get((bucket or self.bucket, key))
        return None if data is None else len(data)

    def put_file(self, key, path, bucket=None):
        self._check()
        if self.fail_on_put:
            raise StoreError(self.fail_on_put)
        data = Path(path).read_bytes()
        self.objects[(bucket or self.bucket, key)] = data
        return len(data)

    def open(self, key, bucket=None):
        self._check()
        data = self.objects.get((bucket or self.bucket, key))
        if data is None:
            raise FileNotFoundError(key)
        return len(data), iter([data[i:i + 4096] for i in range(0, len(data), 4096)] or [b""])

    def download(self, key, dest, bucket=None):
        self._check()
        data = self.objects.get((bucket or self.bucket, key))
        if data is None:
            raise FileNotFoundError(key)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)

    def remove(self, key, bucket=None):
        self._check()
        self.objects.pop((bucket or self.bucket, key), None)

    def read(self, key, bucket=None):
        return self.objects[(bucket or self.bucket, key)]


# ------------------------------------------------------------------ store dùng chung của ứng dụng
_lock = threading.Lock()
_store = None


def get_store() -> PdfStore:
    global _store
    with _lock:
        if _store is None:
            if not (Config.MINIO_ACCESS_KEY and Config.MINIO_SECRET_KEY):
                raise StoreError("Chưa cấu hình MinIO: đặt MINIO_ACCESS_KEY và MINIO_SECRET_KEY trong .env")
            _store = MinioStore(Config.MINIO_ENDPOINT, Config.MINIO_ACCESS_KEY, Config.MINIO_SECRET_KEY,
                                Config.MINIO_BUCKET, Config.MINIO_SECURE, Config.MINIO_REGION)
        return _store


def set_store(store):
    """Thay store dùng chung (test dùng MemoryStore). None = tạo lại từ cấu hình ở lần gọi sau."""
    global _store
    with _lock:
        _store = store


def location(bucket, key):
    """Chuỗi hiển thị vị trí file, vd s3://egazette/pdf/0999999991/AMEND/xxx.pdf"""
    return f"s3://{bucket}/{key}" if bucket and key else ""


