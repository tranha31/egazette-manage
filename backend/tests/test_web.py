"""Test REST API (Flask test client) với dữ liệu đã crawl bằng crawler giả."""
import base64
import io
import itertools
from datetime import date, datetime, timedelta

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app import services
from app.config import Config
from app.db import Session, now
from app.models import Announcement, CrawlJob
from app.web import create_app

from conftest import TAX, needs_pdf, strip_accents

H = {"X-Requested-With": "XMLHttpRequest"}      # header bắt buộc cho thao tác ghi (chống CSRF)


@pytest.fixture()
def client(env, worker):
    return create_app(worker=None, config=Config).test_client()


@pytest.fixture()
def loaded(env, worker):
    """Database đã có 4 bố cáo của công ty mẫu (2024-2026) và đã ghi nhận khoảng crawl."""
    with Session() as s:
        services.submit_request(s, [TAX], ["AMEND"], date(2024, 1, 1), date(2026, 12, 31), now())
    worker.run_pending()


def post(client, url, body=None):
    return client.post(url, json=body, headers=H)


def test_empty_database_endpoints(client):
    for url in ("/api/meta", "/api/worker", "/api/overview", "/api/search", "/api/companies", "/api/people",
                "/api/jobs"):
        r = client.get(url)
        assert r.status_code == 200, url
    assert client.get("/api/overview").get_json()["stats"]["announcements"] == 0
    for url in ("/api/announcements/999", "/api/companies/0000000000", "/api/jobs/999", "/api/files/999",
                "/api/khong-co"):
        r = client.get(url)
        assert r.status_code == 404 and r.is_json and "error" in r.get_json(), url


def test_meta_lists_types_and_statuses(client):
    m = client.get("/api/meta").get_json()
    assert {"code": "AMEND", "name": "Đăng ký thay đổi"} in m["types"] and len(m["types"]) == 7
    assert m["statuses"]["skipped"]["label"] == "Bỏ qua (đã có)" and m["statuses"]["done"]["tone"] == "ok"
    assert m["auth"] is False and m["per_page"] == Config.PER_PAGE


def test_crawl_form_validation(client):
    r = post(client, "/api/crawl", {"tax_codes": "abc 12345", "types": ["AMEND"]})
    assert r.status_code == 400 and "không hợp lệ" in r.get_json()["error"]
    r = post(client, "/api/crawl", {"tax_codes": TAX})
    assert r.status_code == 400 and "loại công bố" in r.get_json()["error"]
    r = post(client, "/api/crawl", {"tax_codes": TAX, "types": ["AMEND"], "date_from": "2025-02-01",
                                    "date_to": "2025-01-01"})
    assert r.status_code == 400 and "nhỏ hơn" in r.get_json()["error"]
    r = post(client, "/api/crawl", {"tax_codes": "", "types": ["AMEND"]})
    assert r.status_code == 400 and r.get_json()["errors"]


def test_mutating_requests_require_ajax_header(client):
    r = client.post("/api/crawl", json={"tax_codes": TAX, "types": ["AMEND"]})      # thiếu header
    assert r.status_code == 400 and "X-Requested-With" in r.get_json()["error"]
    with Session() as s:
        assert s.execute(select(CrawlJob)).first() is None


def test_crawl_submit_creates_job_and_second_submit_is_skipped(client, worker):
    body = {"tax_codes": TAX, "types": ["AMEND"], "date_from": "2024-01-01", "date_to": "2024-12-31"}
    d = post(client, "/api/crawl", body).get_json()
    assert d["queued"] == 1 and d["skipped"] == 0
    r0 = d["results"][0]
    assert r0["needs_crawl"] and r0["job"]["status"] == "queued" and r0["job"]["id"] == 1
    assert r0["job"]["crawl_from"] == "2024-01-01" and r0["job"]["crawl_to"] == "2024-12-31"
    worker.run_pending()
    d = post(client, "/api/crawl", body).get_json()
    assert d["queued"] == 0 and d["skipped"] == 1
    assert d["results"][0]["job"]["status"] == "skipped" and "Đã có" in d["results"][0]["job"]["message"]
    assert d["results"][0]["plan_status"] == "covered"


def test_crawl_accepts_tax_codes_as_list_and_all_types(client):
    d = post(client, "/api/crawl", {"tax_codes": [TAX, "0100109106"], "types": ["ALL"], "date_from": "2024-01-01",
                                    "date_to": "2024-12-31"}).get_json()
    assert len(d["results"]) == 14 and d["queued"] == 14


def test_preview_does_not_create_jobs(client):
    j = {"tax_codes": TAX, "types": ["AMEND", "NEW"], "date_from": "2024-01-01", "date_to": "2024-12-31"}
    items = post(client, "/api/crawl/preview", j).get_json()["items"]
    assert [i["status"] for i in items] == ["missing", "missing"] and items[0]["needs_crawl"]
    with Session() as s:
        assert s.execute(select(CrawlJob)).first() is None
    assert post(client, "/api/crawl/preview", {**j, "date_from": "2025-01-01"}).status_code == 400
    d = post(client, "/api/crawl/preview", {**j, "tax_codes": f"{TAX} abc 12345"}).get_json()
    assert d["invalid"] == ["abc", "12345"] and len(d["items"]) == 2 and d["truncated"] is False


@needs_pdf
def test_search_and_detail(client, loaded, expected):
    def search(**p):
        return client.get("/api/search", query_string=p).get_json()

    d = search(q=expected["search_token"])
    assert d["total"] == expected["counts"]["company"] and d["pages"] == 1 and d["items"][0]["company_name"] == expected["company_name"]
    it = d["items"][0]
    assert it["has_pdf"] and it["ann_type_name"] == "Đăng ký thay đổi" and it["posted_at"].startswith("2026-05-12T17:06")
    assert {r["full_name"] for r in it["reps"]} >= {expected["rep_a"]["name"], expected["rep_b"]["name"]}
    # tìm theo người đại diện / CCCD / địa chỉ
    assert search(q=expected["rep_a"]["id_number"])["total"] == expected["counts"]["rep_a_id"]    # người này không có trong mọi bố cáo
    assert search(q=expected["rep_c"]["name"])["total"] == expected["counts"]["rep_c_name"]
    assert search(q=expected["address_token"])["total"] == expected["counts"]["address_token"]
    # lọc ngày đăng và loại
    assert search(date_from="2026-05-01", date_to="2026-05-31")["total"] == 1
    assert search(ann_type="NEW")["total"] == 0 and search(q="khong-ton-tai-xyz")["total"] == 0
    assert search(q="100%_")["total"] == 0                  # ký tự đặc biệt của LIKE không làm hỏng truy vấn
    assert search(page="abc")["page"] == 1

    ann_id = it["id"]
    a = client.get(f"/api/announcements/{ann_id}").get_json()
    names = {g["name"] for g in a["groups"]}
    assert "Thông tin chung" in names and any("Ngành, nghề" in n for n in names)
    assert any(n.startswith("Người đại diện theo pháp luật") for n in names)
    rep = next(r for r in a["reps"] if r["full_name"] == expected["rep_a"]["name"])
    assert rep["id_number"] == expected["rep_a"]["id_number"] and rep["gender"] == expected["rep_a"]["gender"]
    assert expected["address_token"] in a["hq_address"] and a["parse_status"] == "ok"

    pdf = client.get(f"/api/files/{ann_id}")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf" and pdf.data[:4] == b"%PDF"
    assert "attachment" in client.get(f"/api/files/{ann_id}?download=1").headers["Content-Disposition"]


@needs_pdf
def test_pagination(client, loaded, monkeypatch):
    monkeypatch.setattr(Config, "PER_PAGE", 3)
    p1 = client.get("/api/search?page=1").get_json()
    p2 = client.get("/api/search?page=2").get_json()
    assert p1["total"] == 4 and p1["pages"] == 2 and len(p1["items"]) == 3 and len(p2["items"]) == 1
    assert {i["id"] for i in p1["items"]}.isdisjoint(i["id"] for i in p2["items"])


@needs_pdf
def test_per_page_parameter(client, loaded):
    d = client.get("/api/search?per_page=2&page=2").get_json()
    assert d["per_page"] == 2 and d["pages"] == 2 and d["page"] == 2 and len(d["items"]) == 2
    assert client.get("/api/search?per_page=0").get_json()["per_page"] == 1               # kẹp về tối thiểu
    assert client.get("/api/search?per_page=99999").get_json()["per_page"] == 200         # và tối đa
    assert client.get("/api/search?per_page=abc").get_json()["per_page"] == Config.PER_PAGE
    assert client.get("/api/people?per_page=3").get_json()["per_page"] == 3
    assert client.get("/api/companies?per_page=5").get_json()["per_page"] == 5
    assert client.get("/api/jobs?per_page=7").get_json()["per_page"] == 7


@needs_pdf
def test_deep_search_looks_in_all_fields(client, loaded):
    q = "Lập trình máy tính khác"       # chỉ nằm trong bảng key-value, không nằm ở cột tóm tắt
    assert client.get("/api/search", query_string={"q": q}).get_json()["total"] == 0
    assert client.get("/api/search", query_string={"q": q, "deep": "1"}).get_json()["total"] > 0


@needs_pdf
def test_company_people_and_coverage(client, loaded, expected):
    d = client.get("/api/companies", query_string={"q": expected["search_token"]}).get_json()
    assert d["total"] == 1 and d["items"][0]["tax_code"] == TAX and d["items"][0]["count"] == expected["counts"]["company"]
    assert d["items"][0]["company_name"] == expected["company_name"] and expected["rep_c"]["name"] in d["items"][0]["reps"]
    c = client.get(f"/api/companies/{TAX}").get_json()
    assert len(c["announcements"]) == 4 and c["latest"]["tax_code"] == TAX
    cov = c["coverage"][0]
    assert cov["ann_type"] == "AMEND" and cov["date_from"] == "2024-01-01" and cov["result_count"] == 4
    assert cov["effective"]["start"] == "2024-01-01" and cov["effective"]["end"]    # hôm nay chưa tính -> tới hôm qua/hôm nay
    p = client.get("/api/people", query_string={"name": expected["rep_c"]["name"]}).get_json()
    assert p["total"] == expected["counts"]["rep_c_name"] and p["items"][0]["id_number"] == expected["rep_c"]["id_number"]
    assert p["items"][0]["announcement"]["tax_code"] == TAX
    p = client.get("/api/people", query_string={"id_number": expected["rep_a"]["id_number"]}).get_json()
    assert p["items"][0]["full_name"] == expected["rep_a"]["name"]


@needs_pdf
def test_vietnamese_search_ignores_case_and_accents_on_mysql(client, loaded, expected):
    """Chỉ chạy trên MySQL (utf8mb4_unicode_ci). SQLite chỉ không phân biệt hoa/thường với chữ ASCII."""
    from app import db
    if db.engine().dialect.name != "mysql":
        pytest.skip("chỉ MySQL")
    name = expected["rep_c"]["name"]
    for q in (name.lower(), strip_accents(name).lower()):           # chữ thường có dấu / không dấu
        assert client.get("/api/search", query_string={"q": q}).get_json()["total"] == expected["counts"]["rep_c_name"]
    assert client.get("/api/people", query_string={"name": name.lower()}).get_json()["total"] == expected["counts"]["rep_c_name"]


@needs_pdf
def test_export_excel(client, loaded, expected):
    r = client.get("/api/search/export.xlsx", query_string={"q": expected["search_token"]})
    assert r.status_code == 200 and r.mimetype.endswith("spreadsheetml.sheet")
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["Bố cáo", "Người đại diện"]
    assert wb["Bố cáo"].max_row == 5 and wb["Người đại diện"].max_row > 5
    assert wb["Bố cáo"]["E2"].value == expected["company_name"]


def test_jobs_endpoints_and_actions(client, worker):
    post(client, "/api/crawl", {"tax_codes": TAX, "types": ["AMEND"], "date_from": "2024-01-01", "date_to": "2024-12-31"})
    d = client.get("/api/jobs").get_json()
    assert d["total"] == 1 and d["items"][0]["status"] == "queued" and "log" not in d["items"][0]
    assert client.get("/api/jobs?status=done").get_json()["total"] == 0
    j = client.get("/api/jobs/1").get_json()
    assert j["tax_code"] == TAX and j["log"] == ""
    c = post(client, "/api/jobs/1/cancel").get_json()
    assert c["status"] == "cancelled" and "huỷ" in c["message"]
    r = post(client, "/api/jobs/2/cancel")
    assert r.status_code == 404
    n = post(client, "/api/jobs/1/retry").get_json()               # chạy lại -> job mới
    assert n["id"] == 2 and n["status"] == "queued"


def test_worker_status_and_resume(env, worker):
    c = create_app(worker=worker, config=Config).test_client()
    assert c.get("/api/worker").get_json()["paused"] is False
    worker.paused, worker.pause_reason = True, "Hết tiền"
    s = c.get("/api/worker").get_json()
    assert s["paused"] is True and s["reason"] == "Hết tiền"
    assert post(c, "/api/worker/resume").get_json()["paused"] is False


_seq = itertools.count(1)


def add_announcement(**kw):
    # mỗi bố cáo một thời điểm đăng cố định, không phụ thuộc đồng hồ (khoá duy nhất tax + loại + giờ đăng)
    posted = datetime(2026, 1, 1, 12, 0, 0) + timedelta(seconds=next(_seq))
    with Session() as s:
        a = Announcement(tax_code=TAX, ann_type="AMEND", posted_at=posted, posted_date=posted.date(),
                         created_at=now(), updated_at=now(), pdf_status="ok", **kw)
        s.add(a)
        s.commit()
        return a.id, a.posted_at


def test_pdf_is_streamed_from_minio(client, store):
    store.objects[(store.bucket, "pdf/x/y.pdf")] = b"%PDF-1.4 " + b"x" * 10000
    aid, posted = add_announcement(pdf_bucket=store.bucket, pdf_path="pdf/x/y.pdf", pdf_size=10009)
    r = client.get(f"/api/files/{aid}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data == store.objects[(store.bucket, "pdf/x/y.pdf")]
    assert r.headers["Content-Length"] == "10009"
    assert r.headers["Content-Disposition"] == f'inline; filename="{TAX}_AMEND_{posted:%Y%m%d_%H%M%S}.pdf"'
    dl = client.get(f"/api/files/{aid}?download=1")
    assert dl.headers["Content-Disposition"].startswith("attachment;") and dl.data == r.data


def test_pdf_endpoint_never_touches_paths_outside_what_the_database_says(client, store):
    # key lưu trong DB mới là thứ được đọc; ?path= / ?key= từ người dùng bị bỏ qua
    store.objects[(store.bucket, "pdf/a.pdf")] = b"%PDF-A"
    store.objects[(store.bucket, "secret.txt")] = b"BI MAT"
    aid, _ = add_announcement(pdf_bucket=store.bucket, pdf_path="pdf/a.pdf")
    r = client.get(f"/api/files/{aid}?path=secret.txt&key=secret.txt&bucket=other")
    assert r.data == b"%PDF-A"


def test_pdf_endpoint_error_cases(client, store):
    aid, _ = add_announcement(pdf_bucket="", pdf_path="pdf/legacy.pdf")               # chưa chuyển lên MinIO
    r = client.get(f"/api/files/{aid}")
    assert r.status_code == 404 and "chưa có file PDF trên MinIO" in r.get_json()["error"]
    aid, _ = add_announcement(pdf_bucket=store.bucket, pdf_path="pdf/missing.pdf")    # DB có nhưng object đã mất
    r = client.get(f"/api/files/{aid}")
    assert r.status_code == 404 and "đã bị xoá" in r.get_json()["error"]
    store.fail = "connection refused"                                                 # MinIO sập
    aid, _ = add_announcement(pdf_bucket=store.bucket, pdf_path="pdf/a.pdf")
    r = client.get(f"/api/files/{aid}")
    assert r.status_code == 502 and "connection refused" in r.get_json()["error"]
    assert client.get("/api/files/9999").status_code == 404


def test_has_pdf_requires_the_file_to_be_on_minio(client, store):
    add_announcement(pdf_bucket="", pdf_path="pdf/legacy.pdf")
    add_announcement(pdf_bucket=store.bucket, pdf_path="pdf/ok.pdf", pdf_size=5)
    items = {i["has_pdf"] for i in client.get("/api/search").get_json()["items"]}
    assert items == {True, False}
    d = client.get("/api/announcements/2").get_json()
    assert d["pdf_location"] == f"s3://{store.bucket}/pdf/ok.pdf" and d["pdf_bucket"] == store.bucket
    assert d["pdf_key"] == "pdf/ok.pdf" and d["pdf_size"] == 5
    assert client.get("/api/announcements/1").get_json()["pdf_location"] == ""


def test_basic_auth_when_configured(env, monkeypatch):
    monkeypatch.setattr(Config, "APP_USER", "admin")
    monkeypatch.setattr(Config, "APP_PASSWORD", "s3cret")
    c = create_app(worker=None, config=Config).test_client()
    r = c.get("/api/meta")
    assert r.status_code == 401 and "Basic" in r.headers["WWW-Authenticate"]
    ok = {"Authorization": "Basic " + base64.b64encode(b"admin:s3cret").decode()}
    bad = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()}
    assert c.get("/api/meta", headers=ok).status_code == 200
    assert c.get("/api/meta", headers=bad).status_code == 401
    assert c.get("/", headers=bad).status_code == 401          # cả giao diện cũng cần đăng nhập
    assert c.get("/api/meta", headers=ok).get_json()["auth"] is True


def test_cors_only_for_allowed_origins(env, monkeypatch):
    monkeypatch.setattr(Config, "CORS_ORIGINS", ["https://app.example.com"])
    c = create_app(worker=None, config=Config).test_client()
    ok = c.get("/api/meta", headers={"Origin": "https://app.example.com"})
    assert ok.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
    assert "Access-Control-Allow-Origin" not in c.get("/api/meta", headers={"Origin": "https://evil.example"}).headers
    pre = c.options("/api/crawl", headers={"Origin": "https://app.example.com",
                                           "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 204 and "X-Requested-With" in pre.headers["Access-Control-Allow-Headers"]
    bad = c.options("/api/crawl", headers={"Origin": "https://evil.example"})
    assert bad.status_code == 204 and "Access-Control-Allow-Origin" not in bad.headers


def test_serves_built_frontend_with_spa_fallback(env, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(Config, "FRONTEND_DIST", dist)
    c = create_app(worker=None, config=Config).test_client()
    assert b"SPA" in c.get("/").data
    assert b"SPA" in c.get(f"/companies/{TAX}").data                  # đường dẫn của React Router
    assert c.get("/assets/app.js").data == b"console.log(1)"
    (tmp_path / "secret.txt").write_text("BÍ MẬT", encoding="utf-8")
    for evil in ("/..%2Fsecret.txt", "/%2e%2e/secret.txt", "/assets/..%2F..%2Fsecret.txt"):
        assert "BÍ MẬT" not in c.get(evil).get_data(as_text=True), evil        # không thoát khỏi thư mục dist
    assert c.get("/api/khong-co").status_code == 404 and c.get("/api/khong-co").is_json


def test_without_built_frontend_root_explains(env, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "FRONTEND_DIST", tmp_path / "khong-co")
    r = create_app(worker=None, config=Config).test_client().get("/")
    assert r.status_code == 200 and r.get_json()["api"] == "/api/meta"
