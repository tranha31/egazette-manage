"""
Worker nền: lần lượt lấy job 'queued' (cũ nhất trước), crawl, lưu database.

- Chỉ 1 job chạy tại một thời điểm (mở 1 trình duyệt, tránh dồn captcha).
- Chỉ ghi nhận khoảng "đã crawl" (CrawlCoverage) khi crawl trọn vẹn và trang trả kết quả hợp lệ.
- Hết tiền / sai key 2captcha -> tạm dừng cả hàng đợi (job chuyển 'paused'), bấm "Tiếp tục" trên web để chạy lại.
"""
import tempfile
import threading
import time
import traceback
from pathlib import Path

from sqlalchemy import select, update

from . import services
from .config import Config
from .crawler import Cancelled, StopRun
from .db import Session, now
from .models import (CANCELLED, DONE, DONE_WARN, FAILED, PAUSED, QUEUED, RUNNING, CrawlJob)
from .pdf_parser import parse_pdf
from .storage import StoreError, get_store

MAX_LOG = 60000


class Worker(threading.Thread):
    def __init__(self, crawler_factory, poll=2.0, idle_close=60.0):
        super().__init__(daemon=True, name="crawl-worker")
        self.crawler_factory = crawler_factory
        self.poll, self.idle_close = poll, idle_close
        self.stop_event = threading.Event()
        self.paused = False
        self.pause_reason = ""
        self.current_job_id = None
        self.cancel_ids = set()
        self._crawler = None
        self._last_used = time.time()

    # ---- điều khiển từ web
    def status(self):
        return {"paused": self.paused, "reason": self.pause_reason, "current_job_id": self.current_job_id,
                "alive": self.is_alive()}

    def resume(self):
        """Bỏ tạm dừng; các job 'paused' quay lại hàng đợi."""
        with Session() as s:
            s.execute(update(CrawlJob).where(CrawlJob.status == PAUSED).values(status=QUEUED))
            s.commit()
        self.paused, self.pause_reason = False, ""

    def cancel(self, job_id):
        self.cancel_ids.add(job_id)

    def stop(self):
        self.stop_event.set()

    # ---- vòng lặp
    def run(self):
        with Session() as s:  # job đang 'running' từ lần chạy trước (tiến trình bị tắt giữa chừng) -> chạy lại
            s.execute(update(CrawlJob).where(CrawlJob.status == RUNNING).values(status=QUEUED))
            s.commit()
        while not self.stop_event.is_set():
            try:
                job_id = None if self.paused else self._next_job_id()
                if job_id is None:
                    self._close_if_idle()
                    self.stop_event.wait(self.poll)
                    continue
                self.process(job_id)
            except Exception:  # noqa: BLE001  (lỗi bất ngờ ở vòng lặp không được làm chết worker)
                traceback.print_exc()
                self.stop_event.wait(self.poll)
        self._close_crawler()

    def run_pending(self, max_jobs=100):
        """Chạy đồng bộ các job đang chờ rồi thoát (dùng cho test / chạy tay), không cần thread."""
        n = 0
        while n < max_jobs and not self.paused:
            job_id = self._next_job_id()
            if job_id is None:
                break
            self.process(job_id)
            n += 1
        self._close_crawler()
        return n

    @staticmethod
    def _next_job_id():
        with Session() as s:
            return s.execute(select(CrawlJob.id).where(CrawlJob.status == QUEUED)
                             .order_by(CrawlJob.id).limit(1)).scalar_one_or_none()

    def _ensure_crawler(self):
        if self._crawler is None:
            self._crawler = self.crawler_factory(Config, print)
            self._crawler.open()
        self._last_used = time.time()
        return self._crawler

    def _close_crawler(self):
        if self._crawler is not None:
            try:
                self._crawler.close()
            finally:
                self._crawler = None

    def _close_if_idle(self):
        if self._crawler is not None and time.time() - self._last_used > self.idle_close:
            self._close_crawler()

    # ---- xử lý một job
    def process(self, job_id):
        s = Session()
        try:
            job = s.get(CrawlJob, job_id)
            if job is None or job.status != QUEUED:
                return
            job.status, job.started_at, job.finished_at = RUNNING, now(), None
            job.result_count = job.new_count = job.pdf_ok = job.pdf_fail = 0
            self._log(s, job, f"Bắt đầu: {job.tax_code} / {job.ann_type}, khoảng trang: "
                              f"{job.crawl_from or 'tất cả'} → {job.crawl_to or ''}")
            self.current_job_id = job.id
            try:
                self._run_job(s, job)
            except StopRun as e:
                s.rollback()
                job = s.get(CrawlJob, job_id)
                job.status, job.message = PAUSED, f"Tạm dừng: {e}"
                self.paused, self.pause_reason = True, str(e)
                self._log(s, job, f"TẠM DỪNG HÀNG ĐỢI: {e}")
            except Cancelled:
                s.rollback()
                job = s.get(CrawlJob, job_id)
                job.status, job.message, job.finished_at = CANCELLED, "Đã huỷ", now()
                self.cancel_ids.discard(job_id)
                self._log(s, job, "Đã huỷ theo yêu cầu")
            except Exception as e:  # noqa: BLE001
                s.rollback()
                job = s.get(CrawlJob, job_id)
                job.status, job.message, job.finished_at = FAILED, f"Lỗi: {e!r}"[:2000], now()
                self._log(s, job, "LỖI: " + "".join(traceback.format_exception_only(type(e), e)).strip())
                # trình duyệt có thể đang ở trạng thái xấu -> mở lại cho job sau
                self._close_crawler()
        finally:
            self.current_job_id = None
            s.close()

    @staticmethod
    def _check_storage():
        """MinIO phải sẵn sàng trước khi crawl: không thì tạm dừng hàng đợi (như hết tiền 2captcha), tránh crawl xong mà không lưu được PDF."""
        try:
            get_store().ensure_bucket()
        except StoreError as e:
            raise StopRun(f"Không kết nối được MinIO ({e}). Kiểm tra MinIO rồi bấm “Tiếp tục”.") from e

    def _run_job(self, s, job):
        self._check_storage()
        crawler = self._ensure_crawler()
        crawler.log = lambda m: self._log(s, job, m)
        crawler.check_balance()
        counts = {"new": 0, "pdf_ok": 0, "pdf_fail": 0}
        store = get_store()

        def handle_row(info, fetch_pdf):
            ann, created = services.upsert_announcement(s, job.tax_code, job.ann_type, info, job.id, now())
            counts["new"] += created
            key = services.storage_rel(job.tax_code, job.ann_type, ann.posted_at)
            # PDF tải về thư mục tạm -> tách nội dung -> upload MinIO -> xoá tạm. Không giữ PDF trên đĩa của backend.
            with tempfile.TemporaryDirectory(prefix="egazette_") as tmp:
                local = Path(tmp) / "bocao.pdf"
                try:
                    fresh = False
                    if store.exists(key) and not job.force:
                        ok, how, size = True, "đã có trên MinIO", store.stat(key)
                    else:
                        ok, how = fetch_pdf(local)
                        size = store.put_file(key, local) if ok else 0
                        fresh = ok
                    if ok:
                        ann.pdf_bucket, ann.pdf_path, ann.pdf_size, ann.pdf_status = store.bucket, key, size, "ok"
                        counts["pdf_ok"] += 1
                        if fresh or created or ann.parse_status != "ok":
                            if not local.exists():
                                store.download(key, local)
                            services.apply_parse(s, ann, parse_pdf(local))
                    else:
                        ann.pdf_status = f"failed: {how}"[:255]
                        counts["pdf_fail"] += 1
                except StoreError as e:        # MinIO lỗi giữa chừng: ghi nhận cho bố cáo này, các bố cáo khác vẫn thử tiếp
                    ann.pdf_status = f"failed: MinIO: {e}"[:255]
                    counts["pdf_fail"] += 1
            s.commit()
            self._log(s, job, f"  {info['time']} | PDF: {ann.pdf_status} | tách: {ann.parse_status or '-'}")

        def should_stop():
            return self.stop_event.is_set() or job.id in self.cancel_ids

        result = crawler.crawl(job.tax_code, job.ann_type, job.crawl_from, job.crawl_to, handle_row, should_stop)

        job.result_count, job.new_count = result.rows, counts["new"]
        job.pdf_ok, job.pdf_fail = counts["pdf_ok"], counts["pdf_fail"]
        job.finished_at = now()
        warn = []
        if result.verified:
            services.record_coverage(s, job, result.rows, now())
            job.status = DONE
            job.message = f"Xong: {result.rows} bố cáo ({counts['new']} mới)."
        else:
            job.status = DONE_WARN
            warn.append("trang không trả bảng kết quả hợp lệ (có thể captcha sai) nên CHƯA ghi nhận khoảng đã crawl")
        if counts["pdf_fail"]:
            job.status = DONE_WARN
            warn.append(f"{counts['pdf_fail']} PDF tải lỗi")
        if warn:
            job.message = (job.message + " " if result.verified else "") + "Lưu ý: " + "; ".join(warn) + "."
        self._log(s, job, job.message)
        s.commit()

    @staticmethod
    def _log(s, job, msg):
        line = f"[{now():%H:%M:%S}] {msg}\n"
        job.log = ((job.log or "") + line)[-MAX_LOG:]
        s.commit()
