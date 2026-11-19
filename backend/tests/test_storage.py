"""PDF trên MinIO: lớp lưu trữ, luồng worker, chuyển PDF cũ từ đĩa, migration cột, và (tuỳ chọn) MinIO thật."""
import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text

from app import db, migrate_pdfs, services, storage
from app.db import Session, now
from app.models import (DONE, DONE_WARN, PAUSED, Announcement, CrawlCoverage, CrawlJob)
from app.storage import MemoryStore, MinioStore, StoreError

from conftest import needs_pdf

TAX = ["0101243150"]
D = date


def submit(s, d_from, d_to, force=False):
    return services.submit_request(s, TAX, ["AMEND"], d_from, d_to, now(), force=force)


# ------------------------------------------------------------------ MemoryStore (cùng hợp đồng với MinioStore)
def test_memory_store_contract(tmp_path):
    st = MemoryStore("b")
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-xyz")
    assert st.stat("k") is None and not st.exists("k")
    assert st.put_file("k", f) == 8 and st.stat("k") == 8 and st.exists("k")
    size, chunks = st.open("k")
    assert size == 8 and b"".join(chunks) == b"%PDF-xyz"
    st.download("k", tmp_path / "sub" / "b.pdf")
    assert (tmp_path / "sub" / "b.pdf").read_bytes() == b"%PDF-xyz"
    with pytest.raises(FileNotFoundError):
        st.open("nope")
    st.remove("k")
    assert not st.exists("k")
    st.fail = "down"
    with pytest.raises(StoreError, match="down"):
        st.stat("k")


def test_get_store_requires_credentials(monkeypatch):
    monkeypatch.setattr(storage.Config, "MINIO_ACCESS_KEY", "")
    monkeypatch.setattr(storage.Config, "MINIO_SECRET_KEY", "")
    storage.set_store(None)
    with pytest.raises(StoreError, match="MINIO_ACCESS_KEY"):
        storage.get_store()


def test_location_string():
    assert storage.location("egazette", "pdf/1.pdf") == "s3://egazette/pdf/1.pdf"
    assert storage.location("", "pdf/1.pdf") == "" and storage.location("b", "") == ""


# ------------------------------------------------------------------ worker + MinIO
@needs_pdf
def test_worker_uploads_every_pdf_and_leaves_nothing_on_disk(env, worker, fake, store, tmp_path, monkeypatch):
    tmp_root = tmp_path / "tmproot"
    tmp_root.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(tmp_root))          # mọi thư mục tạm của worker nằm ở đây
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    with Session() as s:
        anns = s.execute(select(Announcement)).scalars().all()
        assert len(anns) == 4 and all(a.pdf_bucket == store.bucket and a.pdf_status == "ok" for a in anns)
        assert {a.pdf_path for a in anns} == {k for (_, k) in store.objects}
        assert all(a.parse_status == "ok" for a in anns)
    assert list(tmp_root.iterdir()) == []                            # file tạm đã được dọn


@needs_pdf
def test_minio_down_pauses_the_queue_and_resume_continues(env, worker, fake, store):
    store.fail = "connection refused"
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2024, 12, 31))
    worker.run_pending()
    assert worker.paused and "MinIO" in worker.pause_reason
    assert fake.calls == []                                           # chưa crawl gì khi MinIO chưa sẵn sàng
    with Session() as s:
        assert s.execute(select(CrawlJob.status)).scalar_one() == PAUSED
        assert s.execute(select(CrawlCoverage)).first() is None
    store.fail = None
    worker.resume()
    worker.run_pending()
    with Session() as s:
        assert s.execute(select(CrawlJob.status)).scalar_one() == DONE
        assert s.execute(select(Announcement.pdf_bucket)).scalar_one() == store.bucket


@needs_pdf
def test_upload_failure_is_reported_per_pdf(env, worker, fake, store):
    store.fail_on_put = "disk full"
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        assert job.status == DONE_WARN and job.pdf_fail == 4 and job.pdf_ok == 0
        a = s.execute(select(Announcement)).scalars().first()
        assert a.pdf_status.startswith("failed: MinIO") and "disk full" in a.pdf_status and a.pdf_bucket == ""
    assert store.objects == {}


@needs_pdf
def test_existing_object_is_not_uploaded_or_parsed_again(env, worker, fake, store, monkeypatch):
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    puts = []
    orig = store.put_file
    monkeypatch.setattr(store, "put_file", lambda *a, **k: (puts.append(a[0]), orig(*a, **k))[1])
    with Session() as s:
        s.query(CrawlCoverage).delete()                              # ép crawl lại cùng khoảng nhưng KHÔNG đặt force
        s.commit()
        submit(s, D(2024, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    assert puts == [] and len(store.objects) == 4                    # object đã có thì không upload lại
    with Session() as s:
        assert s.execute(select(CrawlJob).order_by(CrawlJob.id.desc())).scalars().first().pdf_ok == 4


@needs_pdf
def test_missing_parse_is_redone_from_the_stored_object(env, worker, fake, store):
    with Session() as s:
        submit(s, D(2026, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    with Session() as s:
        s.query(Announcement).update({"parse_status": ""})
        s.query(CrawlCoverage).delete()
        s.commit()
        submit(s, D(2026, 1, 1), D(2026, 12, 31))
    n_calls = len(fake.calls)
    worker.run_pending()
    assert len(fake.calls) == n_calls + 1
    with Session() as s:
        assert {a.parse_status for a in s.execute(select(Announcement)).scalars()} == {"ok"}


@needs_pdf
def test_force_replaces_the_object(env, worker, fake, store):
    with Session() as s:
        submit(s, D(2026, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    key = next(iter(store.objects))
    store.objects[key] = b"%PDF-hong"                                 # giả lập file hỏng
    with Session() as s:
        submit(s, D(2026, 1, 1), D(2026, 12, 31), force=True)
    worker.run_pending()
    assert len(store.objects[key]) > 1000


# ------------------------------------------------------------------ chuyển PDF cũ trên đĩa lên MinIO
def make_legacy(tmp_path, n=3):
    src = tmp_path / "legacy"
    rows = []
    with Session() as s:
        for i in range(n):
            key = f"pdf/0101243150/AMEND/f{i}.pdf"
            (src / key).parent.mkdir(parents=True, exist_ok=True)
            (src / key).write_bytes(b"%PDF-" + bytes([65 + i]) * (100 + i))
            a = Announcement(tax_code="0101243150", ann_type="AMEND", posted_at=now().replace(second=i), posted_date=now().date(),
                             created_at=now(), updated_at=now(), pdf_status="ok", pdf_path=key)
            s.add(a)
            rows.append(key)
        s.commit()
    return src, rows


def test_migrate_uploads_legacy_pdfs_and_updates_database(env, store, tmp_path):
    src, keys = make_legacy(tmp_path)
    logs = []
    with Session() as s:
        st = migrate_pdfs.migrate(s, src, store, log=logs.append)
    assert st == {"total": 3, "uploaded": 3, "already": 0, "missing": 0, "deleted": 0}
    with Session() as s:
        for a in s.execute(select(Announcement)).scalars():
            assert a.pdf_bucket == store.bucket and a.pdf_size == len(store.read(a.pdf_path))
    assert {k for (_, k) in store.objects} == set(keys)
    assert all((src / k).exists() for k in keys)                      # mặc định không xoá file cục bộ
    with Session() as s:                                              # chạy lại: không còn gì để chuyển
        assert migrate_pdfs.migrate(s, src, store)["total"] == 0


def test_migrate_dry_run_changes_nothing(env, store, tmp_path):
    src, _ = make_legacy(tmp_path)
    with Session() as s:
        st = migrate_pdfs.migrate(s, src, store, dry_run=True)
    assert st["total"] == 3 and st["uploaded"] == 0 and store.objects == {}
    with Session() as s:
        assert {a.pdf_bucket for a in s.execute(select(Announcement)).scalars()} == {""}


def test_migrate_reports_missing_files_and_ignores_paths_outside_source(env, store, tmp_path):
    src, keys = make_legacy(tmp_path, n=2)
    (src / keys[0]).unlink()
    (tmp_path / "secret.pdf").write_bytes(b"%PDF-bimat")
    with Session() as s:
        s.add(Announcement(tax_code="1", ann_type="AMEND", posted_at=now().replace(year=2001), posted_date=date(2001, 1, 1),
                           created_at=now(), updated_at=now(), pdf_status="ok", pdf_path="../secret.pdf"))
        s.commit()
        st = migrate_pdfs.migrate(s, src, store, log=lambda m: None)
    assert st["total"] == 3 and st["uploaded"] == 1 and st["missing"] == 2
    assert [k for (_, k) in store.objects] == [keys[1]]               # file ngoài thư mục nguồn không bị upload
    with Session() as s:
        by_path = {a.pdf_path: a.pdf_bucket for a in s.execute(select(Announcement)).scalars()}
    assert by_path[keys[0]] == "" and by_path["../secret.pdf"] == "" and by_path[keys[1]] == store.bucket


def test_migrate_delete_local_after_verified_upload(env, store, tmp_path):
    src, keys = make_legacy(tmp_path, n=2)
    with Session() as s:
        st = migrate_pdfs.migrate(s, src, store, delete_local=True, log=lambda m: None)
    assert st["deleted"] == 2 and not any((src / k).exists() for k in keys) and len(store.objects) == 2


def test_migrate_does_not_commit_when_upload_size_mismatches(env, store, tmp_path, monkeypatch):
    src, _ = make_legacy(tmp_path, n=1)
    monkeypatch.setattr(store, "stat", lambda key, bucket=None: None)         # MinIO "không thấy" object vừa upload
    with Session() as s:
        with pytest.raises(StoreError, match="không khớp"):
            migrate_pdfs.migrate(s, src, store, log=lambda m: None)
    with Session() as s:
        assert s.execute(select(Announcement.pdf_bucket)).scalar_one() == ""


# ------------------------------------------------------------------ migration cột cho database cũ
def test_migrate_adds_missing_columns_to_an_old_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    old = create_engine(url)
    with old.begin() as c:
        c.execute(text("CREATE TABLE announcements (id INTEGER PRIMARY KEY, tax_code VARCHAR(20), pdf_path VARCHAR(500))"))
        c.execute(text("INSERT INTO announcements (tax_code, pdf_path) VALUES ('0101243150', 'pdf/a.pdf')"))
    old.dispose()
    db.init_engine(url)
    try:
        db.migrate()
        db.migrate()                                                    # chạy lại không lỗi
        cols = {c["name"] for c in inspect(db.engine()).get_columns("announcements")}
        assert {"pdf_bucket", "pdf_size", "pdf_path"} <= cols
        with db.engine().connect() as c:
            row = c.execute(text("SELECT pdf_bucket, pdf_size, pdf_path FROM announcements")).one()
        assert tuple(row) == ("", 0, "pdf/a.pdf")                        # dòng cũ giữ nguyên, cột mới có mặc định
    finally:
        db.engine().dispose()


def test_create_tables_on_a_fresh_database_includes_new_columns(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'new.db'}")
    try:
        db.create_tables()
        cols = {c["name"] for c in inspect(db.engine()).get_columns("announcements")}
        assert {"pdf_bucket", "pdf_path", "pdf_size"} <= cols
    finally:
        db.engine().dispose()


# ------------------------------------------------------------------ MinIO thật (chỉ chạy khi đặt TEST_MINIO_ENDPOINT)
real = pytest.mark.skipif(not os.getenv("TEST_MINIO_ENDPOINT"), reason="đặt TEST_MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY để chạy với MinIO thật")


@pytest.fixture()
def real_store():
    bucket = f"egazette-test-{uuid.uuid4().hex[:10]}"
    st = MinioStore(os.environ["TEST_MINIO_ENDPOINT"], os.environ["TEST_MINIO_ACCESS_KEY"],
                    os.environ["TEST_MINIO_SECRET_KEY"], bucket, secure=os.getenv("TEST_MINIO_SECURE") == "1")
    st.ensure_bucket()
    yield st
    for obj in st.client.list_objects(bucket, recursive=True):
        st.client.remove_object(bucket, obj.object_name)
    st.client.remove_bucket(bucket)


@real
def test_real_minio_roundtrip(real_store, tmp_path):
    st = real_store
    st.ensure_bucket()                                                  # idempotent
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4\n" + os.urandom(200_000))
    key = "pdf/0101243150/AMEND/test.pdf"
    assert st.stat(key) is None and not st.exists(key)
    assert st.put_file(key, f) == f.stat().st_size and st.stat(key) == f.stat().st_size
    size, chunks = st.open(key)
    assert size == f.stat().st_size and b"".join(chunks) == f.read_bytes()
    st.download(key, tmp_path / "x" / "b.pdf")
    assert (tmp_path / "x" / "b.pdf").read_bytes() == f.read_bytes()
    with pytest.raises(FileNotFoundError):
        st.open("khong/co.pdf")
    assert st.stat(key, bucket="bucket-khong-ton-tai-xyz") is None
    st.remove(key)
    assert not st.exists(key)


@real
@needs_pdf
def test_real_minio_worker_flow(env, worker, fake, real_store):
    """Toàn luồng với MinIO thật: crawl (giả) -> thư mục tạm -> tách -> upload -> database lưu bucket/key."""
    storage.set_store(real_store)
    with Session() as s:
        submit(s, D(2024, 1, 1), D(2026, 12, 31))
    worker.run_pending()
    with Session() as s:
        job = s.execute(select(CrawlJob)).scalar_one()
        assert job.status == DONE and job.pdf_ok == 4 and job.pdf_fail == 0
        for a in s.execute(select(Announcement)).scalars():
            assert a.pdf_bucket == real_store.bucket and a.parse_status == "ok"
            assert real_store.stat(a.pdf_path) == a.pdf_size > 1000
            size, chunks = real_store.open(a.pdf_path)
            assert b"".join(chunks)[:4] == b"%PDF"


@real
def test_real_minio_errors_are_wrapped():
    ep = os.environ["TEST_MINIO_ENDPOINT"]
    bad = MinioStore(ep, os.environ["TEST_MINIO_ACCESS_KEY"], "sai-mat-khau-xxxx", "egazette-test-x")
    with pytest.raises(StoreError):
        bad.ensure_bucket()
    down = MinioStore("127.0.0.1:1", "a", "b" * 8, "egazette-test-x")
    with pytest.raises(StoreError):
        down.ensure_bucket()
