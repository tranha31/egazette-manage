"""Fixture dùng chung. Mặc định test chạy trên SQLite tạm; đặt TEST_DATABASE_URL để chạy trên MySQL."""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, storage             # noqa: E402
from app.storage import MemoryStore     # noqa: E402
from app.config import Config           # noqa: E402
from app.crawler import CrawlResult, StopRun   # noqa: E402
from app.models import Base             # noqa: E402
from app.services import parse_posted   # noqa: E402
from app.worker import Worker           # noqa: E402

# MST giả dùng làm khoá tra cứu trong test (không phải doanh nghiệp thật)
TAX = "0999999991"

# PDF thật của một công ty mẫu (đã tải bằng tool cũ) dùng để test phần tách. Các giá trị mong đợi (tên công ty, người đại diện...)
# nằm trong SAMPLE_DIR/expected.json, ngoài repo, để dữ liệu thật không đi vào mã nguồn.
# Thiếu thư mục hoặc expected.json thì các test cần PDF tự bỏ qua.
SAMPLE_DIR = Path(os.getenv("SAMPLE_PDF_DIR",
                            r"D:\TTQLDL\outsource\Tool auto search taxcode\output\pdf"))


def _load_expected():
    f = SAMPLE_DIR / "expected.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except (OSError, ValueError):
        return None


EXPECTED = _load_expected()
SAMPLE_FILES = EXPECTED["files"] if EXPECTED else []      # [(nhãn "Thời gian" trên trang, tên file PDF mẫu)]
needs_pdf = pytest.mark.skipif(not (EXPECTED and (SAMPLE_DIR / SAMPLE_FILES[0][1]).exists()),
                               reason="không có PDF mẫu + expected.json (SAMPLE_PDF_DIR)")


def strip_accents(s):
    """'TRẦN THỊ VÍ DỤ' -> 'TRAN THI VI DU' (để thử tìm kiếm không dấu)."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D")) if not unicodedata.combining(c))


class FakeCrawler:
    """Giả lập trang bố cáo: lọc theo khoảng ngày như trang thật, "tải" PDF bằng cách copy file mẫu."""

    def __init__(self, rows):
        self.rows = rows            # {(tax, typ): [(label, pdf_path|None)]}
        self.calls = []             # [(tax, typ, site_from, site_to)]
        self.opened = False
        self.verified = True
        self.raise_on_crawl = None
        self.balance_error = None
        self.log = print

    def open(self):
        self.opened = True

    def close(self):
        self.opened = False

    def check_balance(self):
        if self.balance_error:
            raise StopRun(self.balance_error)

    def crawl(self, tax, typ, site_from, site_to, handle_row, should_stop=lambda: False):
        self.calls.append((tax, typ, site_from, site_to))
        if self.raise_on_crawl:
            raise self.raise_on_crawl
        n = 0
        for label, pdf in self.rows.get((tax, typ), []):
            d = parse_posted(label).date()
            if site_from and d < site_from or site_to and d > site_to:
                continue
            info = {"time": label, "start": "", "end": "", "name_code": f"CÔNG TY TEST MÃ SỐ DN: {tax}",
                    "place": "Thành phố Hà Nội", "type": "Thay đổi nội dung ĐKDN"}

            def fetch(dest, _pdf=pdf):
                if _pdf is None:
                    return False, "không có file"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(_pdf, dest)
                return True, "fake"
            handle_row(info, fetch)
            n += 1
        return CrawlResult(rows=n, verified=self.verified)


@pytest.fixture()
def store():
    """MinIO giả trong bộ nhớ: test không bao giờ chạm tới MinIO thật."""
    st = MemoryStore("egazette-test")
    storage.set_store(st)
    yield st
    storage.set_store(None)


@pytest.fixture()
def env(tmp_path, monkeypatch, store):
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setattr(Config, "DATABASE_URL", url)
    monkeypatch.setattr(Config, "TODAY_RECHECK_MINUTES", 60)
    engine = db.init_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield tmp_path
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def expected():
    return EXPECTED


@pytest.fixture()
def sample_rows():
    rows = [(label, SAMPLE_DIR / f if (SAMPLE_DIR / f).exists() else None) for label, f in SAMPLE_FILES]
    return {(TAX, "AMEND"): rows}


@pytest.fixture()
def fake(sample_rows):
    return FakeCrawler(sample_rows)


@pytest.fixture()
def worker(fake):
    return Worker(lambda cfg, log: fake)


@pytest.fixture()
def now_():
    return db.now()
