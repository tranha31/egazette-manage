"""Phần mã phục vụ chạy trong Docker/Linux: thư mục font, trình duyệt dự phòng, tin reverse proxy."""
import pytest
from sqlalchemy import select

from app import crawler as crawler_mod, pdf_parser
from app.config import Config
from app.db import Session
from app.models import CrawlJob
from app.web import create_app

from conftest import SAMPLE_DIR, MISA_ROWS, needs_pdf

H = {"X-Requested-With": "XMLHttpRequest"}


# ------------------------------------------------------------------ PDF_FONT_DIR
def test_font_dir_defaults_to_windows_and_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.delenv("PDF_FONT_DIR", raising=False)
    monkeypatch.setenv("WINDIR", r"D:\Win")
    assert str(pdf_parser.font_dir()).replace("\\", "/").endswith("Win/Fonts")
    monkeypatch.setenv("PDF_FONT_DIR", str(tmp_path))
    assert pdf_parser.font_dir() == tmp_path
    monkeypatch.setenv("PDF_FONT_DIR", "")                      # biến rỗng = coi như không đặt
    assert str(pdf_parser.font_dir()).replace("\\", "/").endswith("Win/Fonts")


def test_missing_fonts_give_an_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PDF_FONT_DIR", str(tmp_path))
    pdf_parser._gid_to_char.cache_clear()
    try:
        with pytest.raises(FileNotFoundError, match="PDF_FONT_DIR"):
            pdf_parser._gid_to_char("")
    finally:
        pdf_parser._gid_to_char.cache_clear()


@needs_pdf
def test_parse_works_with_fonts_taken_from_pdf_font_dir(monkeypatch, tmp_path):
    """Giả lập container: chép 4 file font vào thư mục riêng và trỏ PDF_FONT_DIR tới đó."""
    import os
    import shutil
    from pathlib import Path
    win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if not all((win / f).exists() for f in pdf_parser.FONT_FILES.values()):
        pytest.skip("máy không có font Times New Roman của Windows")
    for f in pdf_parser.FONT_FILES.values():
        shutil.copyfile(win / f, tmp_path / f)
    monkeypatch.setenv("WINDIR", str(tmp_path / "khong-co"))    # chứng minh không còn đọc từ Windows
    monkeypatch.setenv("PDF_FONT_DIR", str(tmp_path))
    pdf_parser._gid_to_char.cache_clear()
    try:
        r = pdf_parser.parse_pdf(SAMPLE_DIR / MISA_ROWS[0][1])
    finally:
        pdf_parser._gid_to_char.cache_clear()
    assert r["ok"] and any(x["value"] == "CÔNG TY CỔ PHẦN MISA" for x in r["rows"])


# ------------------------------------------------------------------ trình duyệt dự phòng
class FakePlaywright:
    def __init__(self, working_channel):
        self.tried = []
        self.stopped = False
        self.working = working_channel
        outer = self

        class Chromium:
            def launch(self, headless, channel):
                outer.tried.append(channel)
                if channel != outer.working:
                    raise RuntimeError(f"no {channel}")
                return Browser()

        class Browser:
            def new_context(self, **kw):
                return type("Ctx", (), {"new_page": lambda s: "PAGE"})()

        self.chromium = Chromium()

    def stop(self):
        self.stopped = True


def patch_playwright(monkeypatch, fake):
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: type("S", (), {"start": lambda s: fake})())
    monkeypatch.setattr("twocaptcha.TwoCaptcha", lambda key: object())


def test_crawler_falls_back_to_playwright_chromium(monkeypatch):
    fake = FakePlaywright(working_channel=None)                    # trong Docker: không có Chrome/Edge
    patch_playwright(monkeypatch, fake)
    c = crawler_mod.PlaywrightCrawler("key")
    c.open()
    assert fake.tried == ["chrome", "msedge", None] and c.page == "PAGE"


def test_crawler_prefers_installed_chrome(monkeypatch):
    fake = FakePlaywright(working_channel="chrome")
    patch_playwright(monkeypatch, fake)
    crawler_mod.PlaywrightCrawler("key").open()
    assert fake.tried == ["chrome"]


def test_crawler_reports_when_no_browser_works(monkeypatch):
    fake = FakePlaywright(working_channel="khong-co")
    patch_playwright(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="Chromium của Playwright"):
        crawler_mod.PlaywrightCrawler("key").open()
    assert fake.stopped


# ------------------------------------------------------------------ reverse proxy
def test_client_ip_comes_from_forwarded_header_only_when_proxy_is_trusted(env, monkeypatch):
    body = {"tax_codes": "0101243150", "types": ["AMEND"], "date_from": "2024-01-01", "date_to": "2024-12-31"}
    fwd = {**H, "X-Forwarded-For": "203.0.113.7"}

    monkeypatch.setattr(Config, "TRUST_PROXY", True)
    c = create_app(worker=None, config=Config).test_client()
    assert c.post("/api/crawl", json=body, headers=fwd).status_code == 200
    with Session() as s:
        assert s.execute(select(CrawlJob.created_by)).scalar_one() == "203.0.113.7"

    monkeypatch.setattr(Config, "TRUST_PROXY", False)               # không tin proxy: header giả bị bỏ qua
    c = create_app(worker=None, config=Config).test_client()
    body["date_from"] = "2023-01-01"
    body["date_to"] = "2023-12-31"
    assert c.post("/api/crawl", json=body, headers=fwd).status_code == 200
    with Session() as s:
        ips = s.execute(select(CrawlJob.created_by).order_by(CrawlJob.id)).scalars().all()
    assert ips[0] == "203.0.113.7" and ips[1] != "203.0.113.7"
