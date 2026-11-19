"""Test toàn luồng: yêu cầu -> kiểm tra đã có chưa -> crawl (giả) -> lưu database -> crawl lại."""
from datetime import date

from sqlalchemy import func, select

from app import services
from app.crawler import StopRun
from app.db import Session
from app.models import (CANCELLED, DONE, DONE_WARN, FAILED, PAUSED, QUEUED, SKIPPED, Announcement,
                        AnnouncementField, CrawlCoverage, CrawlJob, LegalRep)

from conftest import TAX as TAX_CODE, needs_pdf

TAX = [TAX_CODE]
D = date


def submit(s, d_from=None, d_to=None, force=False, types=("AMEND",), now=None):
    from app.db import now as _now
    return services.submit_request(s, TAX, list(types), d_from, d_to, now or _now(), force=force)


def count(s, model):
    return s.execute(select(func.count()).select_from(model)).scalar_one()


@needs_pdf
def test_first_request_crawls_and_saves_everything(env, worker, fake, store, expected):
    with Session() as s:
        res = submit(s, D(2024, 1, 1), D(2026, 12, 31))
        assert [r.job.status for r in res] == [QUEUED]
    assert worker.run_pending() == 1
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        assert job.status == DONE and job.result_count == 4 and job.pdf_ok == 4   # 4 bố cáo từ 2024 trở đi
        assert count(s, Announcement) == 4 and count(s, CrawlCoverage) == 1
        assert count(s, LegalRep) > 0 and count(s, AnnouncementField) > 100
        a = s.execute(select(Announcement).order_by(Announcement.posted_at.desc())).scalars().first()
        assert a.posted_at.hour == 17 and a.posted_at.minute == 6          # "5:06:00 CH" = 17:06
        assert a.company_name == expected["company_name"] and a.doc_tax_code == expected["tax_code"]
        assert expected["address_token"] in a.hq_address and a.parse_status == "ok" and a.pdf_status == "ok"
        assert {r.full_name for r in a.reps} >= {expected["rep_a"]["name"], expected["rep_b"]["name"]}
        assert any(r.id_number == expected["rep_a"]["id_number"] and r.gender == expected["rep_a"]["gender"] for r in a.reps)
        # PDF nằm trên MinIO; database lưu bucket + object key + kích thước, không còn đường dẫn đĩa
        assert a.pdf_bucket == store.bucket and a.pdf_path == (
            f"pdf/{TAX_CODE}/AMEND/{TAX_CODE}_AMEND_{a.posted_at:%Y%m%d_%H%M%S}.pdf")
        assert store.read(a.pdf_path)[:4] == b"%PDF" and a.pdf_size == len(store.read(a.pdf_path)) > 1000
        assert len(store.objects) == 4
    assert fake.calls == [(TAX_CODE, "AMEND", D(2024, 1, 1), _today())]


def _today():
    from app.db import now
    return now().date()


@needs_pdf
def test_identical_request_is_skipped_without_crawling(env, worker, fake):
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    n_calls = len(fake.calls)
    with Session() as s:
        res = submit(s, D(2024, 1, 1), D(2024, 12, 31))
        assert res[0].skipped and res[0].job.status == SKIPPED and "Đã có" in res[0].job.message
    assert worker.run_pending() == 0 and len(fake.calls) == n_calls


@needs_pdf
def test_sub_range_is_skipped(env, worker, fake):
    with Session() as s:
        submit(s, D(2022, 1, 1), D(2025, 12, 31))
    worker.run_pending()
    with Session() as s:
        assert submit(s, D(2024, 6, 1), D(2024, 12, 31))[0].skipped
        assert submit(s, D(2022, 1, 1), D(2025, 12, 31))[0].skipped


@needs_pdf
def test_extended_range_only_crawls_the_missing_part(env, worker, fake):
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    with Session() as s:
        res = submit(s, D(2024, 1, 1), D(2025, 12, 31))
        job = res[0].job
        assert job.status == QUEUED and (job.crawl_from, job.crawl_to) == (D(2025, 1, 1), D(2025, 12, 31))
        assert "bổ sung" in job.message
    worker.run_pending()
    assert fake.calls[-1] == (TAX_CODE, "AMEND", D(2025, 1, 1), D(2025, 12, 31))
    with Session() as s:   # sau đó cả khoảng đã được phủ
        assert submit(s, D(2024, 1, 1), D(2025, 12, 31))[0].skipped
        assert count(s, Announcement) == 2        # 05/11/2024 và 10/05/2025


@needs_pdf
def test_overlapping_crawl_does_not_duplicate_announcements(env, worker, fake):
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2025, 12, 31))
    worker.run_pending()
    with Session() as s:
        n_fields = count(s, AnnouncementField)
        submit(s, D(2024, 1, 1), D(2025, 12, 31), force=True)   # ép crawl lại đúng khoảng đó
    worker.run_pending()
    with Session() as s:
        assert count(s, Announcement) == 2 and count(s, AnnouncementField) == n_fields   # không nhân đôi


@needs_pdf
def test_force_bypasses_the_check(env, worker, fake):
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    with Session() as s:
        res = submit(s, D(2024, 1, 1), D(2024, 12, 31), force=True)
        assert res[0].job.status == QUEUED
    worker.run_pending()
    assert len(fake.calls) == 2


def test_pending_jobs_prevent_duplicate_requests(env):
    with Session() as s:
        first = submit(s, D(2024, 1, 1), D(2024, 12, 31))
        second = submit(s, D(2024, 3, 1), D(2024, 6, 30))      # nằm trong job đang chờ
        assert first[0].job.status == QUEUED and second[0].skipped
        third = submit(s, D(2024, 1, 1), D(2025, 6, 30))       # chỉ phần ngoài job đang chờ
        assert (third[0].job.crawl_from, third[0].job.crawl_to) == (D(2025, 1, 1), D(2025, 6, 30))


@needs_pdf
def test_no_date_request_crawls_all_then_only_new_days(env, worker, fake):
    with Session() as s:
        res = submit(s)
        assert res[0].job.crawl_from is None and res[0].job.crawl_to is None      # không lọc ngày
    worker.run_pending()
    assert fake.calls[-1][2:] == (None, None)
    with Session() as s:
        assert count(s, Announcement) == 5
        # vừa crawl xong -> yêu cầu lại ngay: trong cửa sổ TODAY_RECHECK nên coi hôm nay đã đủ
        assert submit(s)[0].skipped


@needs_pdf
def test_unverified_result_does_not_record_coverage(env, worker, fake):
    fake.verified = False       # ví dụ captcha sai: trang không trả bảng kết quả
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        assert job.status == DONE_WARN and "CHƯA ghi nhận" in job.message
        assert count(s, CrawlCoverage) == 0
        assert submit(s, D(2024, 1, 1), D(2024, 12, 31))[0].job.status == QUEUED   # vẫn phải crawl lại


def test_failed_job_does_not_record_coverage(env, worker, fake):
    fake.raise_on_crawl = RuntimeError("trang không phản hồi")
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        assert job.status == FAILED and "trang không phản hồi" in job.message
        assert count(s, CrawlCoverage) == 0


def test_out_of_balance_pauses_queue_and_resume_continues(env, worker, fake):
    fake.balance_error = "Số dư 2captcha chỉ còn 0.0000 USD"
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    assert worker.paused and "Số dư" in worker.pause_reason
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        assert job.status == PAUSED and count(s, CrawlCoverage) == 0
        # job đang tạm dừng vẫn giữ chỗ: yêu cầu trùng không tạo thêm job
        assert submit(s, D(2024, 1, 1), D(2024, 12, 31))[0].skipped
    fake.balance_error = None
    worker.resume()
    assert not worker.paused
    with Session() as s:
        assert s.execute(select(CrawlJob.status).where(CrawlJob.status != SKIPPED)).scalar_one() == QUEUED
    worker.run_pending()
    with Session() as s:
        assert s.execute(select(CrawlJob.status).where(CrawlJob.status == DONE)).scalar_one() == DONE


def test_cancelled_queued_job_releases_its_range(env):
    with Session() as s:
        job = submit(s, D(2024, 1, 1), D(2024, 12, 31))[0].job
        job.status = CANCELLED
        s.commit()
        assert submit(s, D(2024, 1, 1), D(2024, 12, 31))[0].job.status == QUEUED


def test_missing_pdf_is_recorded_as_warning(env, worker, fake):
    fake.rows = {(TAX_CODE, "AMEND"): [("12/05/2026 5:06:00 CH Đăng ký thay đổi", None)]}   # không tải được PDF
    with Session() as s:
        submit(s, D(2026, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        a = s.execute(select(Announcement)).scalar_one()
        assert job.status == DONE_WARN and job.pdf_fail == 1 and a.pdf_status.startswith("failed")
        assert count(s, CrawlCoverage) == 1        # danh sách đã đủ nên vẫn ghi nhận khoảng đã crawl


def test_all_types_expands_and_validates(env):
    with Session() as s:
        res = services.submit_request(s, TAX, ["ALL"], D(2024, 1, 1), D(2024, 12, 31), _now())
        assert len(res) == 7
    ok, bad = services.parse_tax_codes(f"{TAX_CODE}, {TAX_CODE[1:]}\n12345 0100109106-001;abc")
    assert ok == [TAX_CODE, "0100109106-001"] and bad == ["12345", "abc"]


def _now():
    from app.db import now
    return now()
