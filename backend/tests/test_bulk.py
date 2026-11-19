"""Crawl hàng loạt từ Excel: file mẫu, đọc/kiểm tra file, xem trước và gửi."""
import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app import bulk, services
from app.config import Config
from app.db import Session, now
from app.models import CrawlJob
from app.web import create_app

from conftest import needs_pdf

H = {"X-Requested-With": "XMLHttpRequest"}
TAX = "0101243150"
HEAD = ["Mã số thuế", "Loại công bố", "Từ ngày", "Đến ngày", "Crawl lại"]


def make_xlsx(rows, head=HEAD, sheet="Input", pre=()):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for p in pre:
        ws.append(p)
    ws.append(head)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def parse(rows, **kw):
    return bulk.parse_workbook(make_xlsx(rows, **kw))


# ------------------------------------------------------------------ file mẫu
def test_template_is_readable_by_the_parser_and_documented():
    data = bulk.make_template()
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Input", "Hướng dẫn"]
    assert [c.value for c in wb["Input"][1]] == HEAD
    guide = " ".join(str(c.value) for row in wb["Hướng dẫn"].iter_rows() for c in row if c.value)
    assert "AMEND" in guide and "Đăng ký thay đổi" in guide and "Crawl lại" in guide
    rows = bulk.parse_workbook(io.BytesIO(data))           # hai dòng mẫu phải hợp lệ
    assert [r.ok for r in rows] == [True, True]
    assert rows[0].tax_code == TAX and rows[0].types == ["AMEND"]
    assert (rows[0].date_from, rows[0].date_to) == (date(2024, 1, 1), date(2024, 12, 31)) and rows[0].force is False
    assert len(rows[1].types) == 7 and rows[1].date_from is None          # ALL = đủ 7 loại


# ------------------------------------------------------------------ đọc từng dòng
def test_row_variants_are_normalised():
    rows = parse([
        [101243150, "amend", datetime(2024, 1, 5), "2024-12-31", "Có"],      # MST dạng số mất số 0, ngày dạng Excel và ISO
        ["0100109106-001", "Đăng ký mới", "5/1/2024", "31.12.2024", "x"],  # MST 13 số, tên loại, ngày d/m/yyyy
        ["0101243150", "AMEND, NEW; amend", None, None, ""],               # nhiều loại, trùng được gộp
        ["0101243150", "Tất cả", None, None, "Không"],
    ])
    assert all(r.ok for r in rows), [r.errors for r in rows]
    assert rows[0].tax_code == "0101243150" and rows[0].types == ["AMEND"] and rows[0].force is True
    assert (rows[0].date_from, rows[0].date_to) == (date(2024, 1, 5), date(2024, 12, 31))
    assert rows[1].tax_code == "0100109106-001" and rows[1].types == ["NEW"]
    assert (rows[1].date_from, rows[1].date_to) == (date(2024, 1, 5), date(2024, 12, 31)) and rows[1].force
    assert rows[2].types == ["AMEND", "NEW"] and set(rows[3].types) == set(bulk.TYPES) and rows[3].force is False
    assert [r.line for r in rows] == [2, 3, 4, 5]


@pytest.mark.parametrize("cells, fragment", [
    (["abc", "AMEND", None, None, None], "không hợp lệ"),
    (["12345", "AMEND", None, None, None], "không hợp lệ"),
    ([None, "AMEND", None, None, None], "Thiếu mã số thuế"),
    (["0101243150 0100109106", "AMEND", None, None, None], "một mã số thuế"),
    (["0101243150", None, None, None, None], "Thiếu loại"),
    (["0101243150", "XYZ", None, None, None], "Loại công bố không hợp lệ: 'XYZ'"),
    (["0101243150", "AMEND, XYZ", None, None, None], "'XYZ'"),
    (["0101243150", "AMEND", "31/02/2024", None, None], "Từ ngày phải có dạng"),
    (["0101243150", "AMEND", "hôm qua", None, None], "Từ ngày phải có dạng"),
    (["0101243150", "AMEND", None, "13/13/2024", None], "Đến ngày phải có dạng"),
    (["0101243150", "AMEND", "01/02/2025", "01/01/2025", None], "nhỏ hơn hoặc bằng"),
    (["0101243150", "AMEND", None, None, "có thể"], "Crawl lại chỉ nhận"),
])
def test_invalid_rows_report_a_clear_error(cells, fragment):
    (r,) = parse([cells])
    assert not r.ok and any(fragment in e for e in r.errors), r.errors


def test_one_sided_dates_are_allowed_and_blank_rows_skipped():
    rows = parse([[TAX, "AMEND", "01/01/2024", None, None], [None] * 5, [TAX, "NEW", None, "31/12/2024", None]])
    assert [r.line for r in rows] == [2, 4] and all(r.ok for r in rows)
    assert rows[0].date_to is None and rows[1].date_from is None


def test_duplicate_rows_get_a_warning_not_an_error():
    rows = parse([[TAX, "AMEND", None, None, None], [TAX, "AMEND", None, None, None], [TAX, "AMEND", None, None, "Có"]])
    assert rows[0].warnings == [] and rows[1].ok and "dòng 2" in rows[1].warnings[0]
    assert rows[2].warnings == []                      # khác cột "Crawl lại" nên không phải trùng


def test_header_aliases_extra_columns_and_title_rows():
    rows = parse([[TAX, "AMEND", "x"]], head=["MST", "Loại", "Ghi chú"], pre=[["Danh sách khách hàng"], []])
    assert len(rows) == 1 and rows[0].line == 4 and rows[0].tax_code == TAX      # tìm hàng tiêu đề trong vài dòng đầu
    rows = parse([["AMEND", TAX]], head=["Loại công bố", "Mã số thuế"])          # đổi thứ tự cột
    assert rows[0].tax_code == TAX and rows[0].types == ["AMEND"]
    rows = parse([[TAX, "AMEND"]], head=["  mã số thuế *", "LOẠI CÔNG BỐ:"], sheet="Sheet1")     # sheet khác tên, tiêu đề lệch
    assert rows[0].ok


# ------------------------------------------------------------------ lỗi cả file
def test_file_level_errors():
    with pytest.raises(bulk.BulkError, match=r"\.xlsx"):
        bulk.parse_workbook(io.BytesIO(b"day khong phai file excel"))
    with pytest.raises(bulk.BulkError, match="tiêu đề"):
        parse([[TAX, "AMEND"]], head=["A", "B"])
    with pytest.raises(bulk.BulkError, match="không có dòng dữ liệu"):
        parse([])
    with pytest.raises(bulk.BulkError, match=f"quá {bulk.MAX_ROWS} dòng"):
        parse([[TAX, "AMEND"]] * (bulk.MAX_ROWS + 1))
    with pytest.raises(bulk.BulkError, match="cặp"):
        parse([[f"{i:010d}", "ALL"] for i in range(1, 200)])       # 199 dòng x 7 loại > giới hạn


# ------------------------------------------------------------------ API
@pytest.fixture()
def client(env, worker):
    return create_app(worker=None, config=Config).test_client()


def upload(client, buf, name="mau.xlsx"):
    return client.post("/api/crawl/import", data={"file": (buf, name)}, headers=H, content_type="multipart/form-data")


def test_template_download(client):
    r = client.get("/api/crawl/template.xlsx")
    assert r.status_code == 200 and r.mimetype.endswith("spreadsheetml.sheet")
    assert "egazette_mau_crawl.xlsx" in r.headers["Content-Disposition"]
    assert load_workbook(io.BytesIO(r.data)).sheetnames == ["Input", "Hướng dẫn"]


def test_import_previews_rows_without_creating_jobs(client):
    d = upload(client, make_xlsx([
        [TAX, "AMEND", "01/01/2024", "31/12/2024", None],
        [TAX, "ALL", None, None, None],
        ["abc", "AMEND", None, None, None],
    ])).get_json()
    assert d["filename"] == "mau.xlsx" and d["totals"] == {"rows": 3, "valid": 2, "invalid": 1, "to_run": 8, "to_skip": 0}
    a, b, c = d["rows"]
    assert a["line"] == 2 and a["pairs"][0]["status"] == "missing" and a["to_run"] == 1
    assert len(b["pairs"]) == 7 and b["to_run"] == 7
    assert c["errors"] and c["pairs"] == [] and c["to_run"] == 0
    with Session() as s:
        assert s.execute(select(CrawlJob)).first() is None


def test_import_does_not_count_duplicate_rows(client):
    d = upload(client, make_xlsx([[TAX, "AMEND", None, None, None]] * 2 + [[TAX, "NEW", None, None, None]])).get_json()
    a, b, c = d["rows"]
    assert a["to_run"] == 1 and b["pairs"] == [] and b["to_run"] == 0 and b["warnings"] and c["to_run"] == 1
    assert d["totals"]["to_run"] == 2 and d["totals"]["valid"] == 3


def test_import_rejects_bad_uploads(client):
    assert client.post("/api/crawl/import", data={}, headers=H, content_type="multipart/form-data").status_code == 400
    r = upload(client, io.BytesIO(b"khong phai excel"), "x.xlsx")
    assert r.status_code == 400 and ".xlsx" in r.get_json()["error"]
    r = upload(client, make_xlsx([]))
    assert r.status_code == 400 and "không có dòng dữ liệu" in r.get_json()["error"]
    assert client.post("/api/crawl/import", data={"file": (io.BytesIO(b"x"), "a.xlsx")}).status_code == 400   # thiếu header CSRF


def test_import_rejects_oversized_files(client):
    big = io.BytesIO(b"0" * (5 * 1024 * 1024 + 10))
    r = upload(client, big, "big.xlsx")
    assert r.status_code == 413 and "5 MB" in r.get_json()["error"]


def test_batch_creates_one_job_per_pair_with_each_rows_own_dates(client):
    body = {"rows": [
        {"tax_code": TAX, "types": ["AMEND"], "date_from": "2024-01-01", "date_to": "2024-12-31", "force": False},
        {"tax_code": "0100109106", "types": ["AMEND", "NEW"], "date_from": "2025-01-01", "date_to": "2025-06-30", "force": False},
    ]}
    d = client.post("/api/crawl/batch", json=body, headers=H).get_json()
    assert d["queued"] == 3 and d["skipped"] == 0 and len(d["results"]) == 3
    jobs = [(r["tax_code"], r["ann_type"], r["job"]["crawl_from"], r["job"]["crawl_to"]) for r in d["results"]]
    assert jobs == [(TAX, "AMEND", "2024-01-01", "2024-12-31"), ("0100109106", "AMEND", "2025-01-01", "2025-06-30"),
                    ("0100109106", "NEW", "2025-01-01", "2025-06-30")]


def test_batch_skips_what_is_already_pending(client):
    row = {"tax_code": TAX, "types": ["AMEND"], "date_from": "2024-01-01", "date_to": "2024-12-31"}
    d = client.post("/api/crawl/batch", json={"rows": [row, row]}, headers=H).get_json()      # cùng yêu cầu hai lần
    assert d["queued"] == 1 and d["skipped"] == 1
    with Session() as s:
        assert s.execute(select(CrawlJob.status).order_by(CrawlJob.id)).scalars().all() == ["queued", "skipped"]


def test_batch_validates_on_the_server(client):
    def err(rows):
        r = client.post("/api/crawl/batch", json={"rows": rows}, headers=H)
        assert r.status_code == 400
        return r.get_json()["error"]

    assert "Không có dòng" in err([])
    assert "Dòng 1" in err([{"tax_code": "abc", "types": ["AMEND"]}])
    assert "Dòng 2" in err([{"tax_code": TAX, "types": ["AMEND"]}, {"tax_code": TAX, "types": ["XYZ"]}])
    assert "nhỏ hơn" in err([{"tax_code": TAX, "types": ["AMEND"], "date_from": "2025-02-01", "date_to": "2025-01-01"}])
    assert "giới hạn" in err([{"tax_code": f"{i:010d}", "types": list(bulk.TYPES)} for i in range(1, 200)])
    assert client.post("/api/crawl/batch", json={"rows": [{"tax_code": TAX, "types": ["AMEND"]}]}).status_code == 400   # CSRF
    with Session() as s:
        assert s.execute(select(CrawlJob)).first() is None         # lỗi thì không tạo job nào (kể cả các dòng hợp lệ)


@needs_pdf
def test_import_preview_recognises_what_is_already_in_the_database(client, worker):
    with Session() as s:
        services.submit_request(s, [TAX], ["AMEND"], date(2024, 1, 1), date(2026, 12, 31), now())
    worker.run_pending()
    d = upload(client, make_xlsx([
        [TAX, "AMEND", "01/01/2024", "31/12/2025", None],           # đã có trọn khoảng
        [TAX, "AMEND", "01/01/2024", "31/12/2025", "Có"],           # bắt buộc crawl lại
        [TAX, "NEW", "01/01/2024", "31/12/2025", None],             # loại khác chưa có
    ])).get_json()
    a, b, c = d["rows"]
    assert a["pairs"][0]["status"] == "covered" and a["to_skip"] == 1 and a["to_run"] == 0
    assert b["pairs"][0]["status"] == "forced" and b["to_run"] == 1
    assert c["pairs"][0]["status"] == "missing"
    assert d["totals"]["to_run"] == 2 and d["totals"]["to_skip"] == 1
