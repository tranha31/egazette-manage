"""Flask: REST API (JSON) cho frontend React. Mọi đường dẫn dữ liệu nằm dưới /api.

Nếu thư mục frontend/dist có sẵn (đã `npm run build`) thì backend cũng phục vụ luôn giao diện React ở "/".
Khi dev, chạy frontend riêng bằng `npm run dev` (Vite tự chuyển tiếp /api sang backend).
"""
import hmac
import io
from datetime import date

from flask import Flask, Response, abort, g, jsonify, request, send_file, send_from_directory
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import func, select
from werkzeug.exceptions import HTTPException

from . import bulk, coverage, db, serializers as ser, services
from .config import Config
from .db import Session, create_tables, init_engine, now
from .models import CANCELLED, PAUSED, QUEUED, RUNNING, TYPES, Announcement, CrawlJob
from .storage import StoreError, get_store, location

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MUTATING = ("POST", "PUT", "PATCH", "DELETE")


def parse_iso(s):
    try:
        return date.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def create_app(worker=None, config=Config):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024      # file Excel tải lên tối đa 5 MB
    app.worker = worker
    if config.TRUST_PROXY:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    if db._state["engine"] is None:  # test có thể đã khởi tạo engine riêng (SQLite)
        init_engine(config.DATABASE_URL)
    if config.AUTO_CREATE_TABLES:
        create_tables()

    def is_api():
        return request.path.startswith("/api/") or request.path == "/api"

    def cors_origin():
        o = request.headers.get("Origin", "").rstrip("/")
        return o if o and o in config.CORS_ORIGINS else ""

    # ------------------------------------------------------------ hạ tầng
    @app.before_request
    def _guard():
        origin = cors_origin()
        if request.method == "OPTIONS":          # preflight CORS: không cần đăng nhập
            r = Response(status=204)
            if origin:
                r.headers["Access-Control-Allow-Origin"] = origin
                r.headers["Access-Control-Allow-Credentials"] = "true"
                r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                r.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With, Authorization"
                r.headers["Access-Control-Max-Age"] = "600"
                r.headers["Vary"] = "Origin"
            return r
        if config.APP_USER and config.APP_PASSWORD:
            a = request.authorization
            ok = a and hmac.compare_digest(a.username or "", config.APP_USER) \
                and hmac.compare_digest(a.password or "", config.APP_PASSWORD)
            if not ok:
                return Response('{"error": "Cần đăng nhập"}', 401,
                                {"WWW-Authenticate": 'Basic realm="Egazette"', "Content-Type": "application/json"})
        # Chống CSRF: trình duyệt tự gửi kèm mật khẩu Basic đã nhớ, nên thao tác ghi bắt buộc có header tuỳ chỉnh
        # (trang web lạ muốn gửi header này phải qua preflight CORS, mà ta chỉ cho phép origin trong CORS_ORIGINS).
        if request.method in MUTATING and request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify(error="Thiếu header X-Requested-With: XMLHttpRequest"), 400
        g.s = Session()

    @app.after_request
    def _cors(resp):
        origin = cors_origin()
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
            resp.headers["Vary"] = "Origin"
        return resp

    @app.teardown_request
    def _close(_exc):
        s = g.pop("s", None)
        if s is not None:
            s.close()

    @app.errorhandler(HTTPException)
    def _http_error(e):
        if is_api():
            msg = {404: "Không tìm thấy dữ liệu.", 405: "Phương thức không được hỗ trợ.",
                   413: "File quá lớn (tối đa 5 MB)."}.get(e.code, e.description)
            return jsonify(error=msg), e.code
        return e

    def page_arg():
        try:
            return max(int(request.args.get("page", 1)), 1)
        except ValueError:
            return 1

    def per_page_arg():
        """?per_page=: số dòng mỗi trang, giới hạn 1..200 (mặc định PER_PAGE)."""
        try:
            return min(max(int(request.args.get("per_page", config.PER_PAGE)), 1), 200)
        except ValueError:
            return config.PER_PAGE

    def paged(items, total, page, per):
        return {"items": items, "total": total, "page": page, "per_page": per,
                "pages": max((total + per - 1) // per, 1)}

    def search_filters():
        a = request.args
        return {"q": a.get("q", ""), "deep": a.get("deep") == "1", "tax_code": a.get("tax_code", ""),
                "ann_type": a.get("ann_type", ""), "date_from": parse_iso(a.get("date_from")),
                "date_to": parse_iso(a.get("date_to")), "pdf_only": a.get("pdf_only") == "1"}

    def worker_status():
        return app.worker.status() if app.worker else {"paused": False, "reason": "", "current_job_id": None,
                                                        "alive": False}

    # ------------------------------------------------------------ meta / trạng thái chung
    @app.get("/api/meta")
    def meta():
        return jsonify(ser.meta() | {"per_page": config.PER_PAGE, "auth": bool(config.APP_USER and config.APP_PASSWORD)})

    @app.get("/api/worker")
    def worker_get():
        return jsonify(worker_status())

    @app.post("/api/worker/resume")
    def worker_resume():
        if app.worker:
            app.worker.resume()
        return jsonify(worker_status())

    @app.get("/api/overview")
    def overview():
        s = g.s
        jobs = s.execute(select(CrawlJob).order_by(CrawlJob.id.desc()).limit(8)).scalars().all()
        latest = s.execute(select(Announcement).order_by(Announcement.posted_at.desc()).limit(8)).scalars().all()
        return jsonify(stats=services.stats(s), jobs=[ser.job_dict(j) for j in jobs],
                       latest=[ser.announcement_summary(a) for a in latest])

    # ------------------------------------------------------------ crawl
    @app.post("/api/crawl")
    def crawl():
        j = request.get_json(silent=True) or {}
        errors = []
        raw = j.get("tax_codes", "")
        tax_codes, bad = services.parse_tax_codes("\n".join(raw) if isinstance(raw, list) else str(raw))
        if bad:
            errors.append("Mã số thuế không hợp lệ: " + ", ".join(bad) + " (cần 10 hoặc 13 số, ví dụ 0999999991 hoặc 0999999991-001).")
        if not tax_codes and not bad:
            errors.append("Hãy nhập ít nhất một mã số thuế.")
        types = [t for t in (j.get("types") or []) if t == "ALL" or t in TYPES]
        if not types:
            errors.append("Hãy chọn ít nhất một loại công bố.")
        d_from, d_to = parse_iso(j.get("date_from")), parse_iso(j.get("date_to"))
        if d_from and d_to and d_from > d_to:
            errors.append("'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")
        if len(tax_codes) * (len(TYPES) if "ALL" in types else len(types)) > 200:
            errors.append("Mỗi lần gửi tối đa 200 cặp (MST × loại công bố).")
        if errors:
            return jsonify(error=errors[0], errors=errors), 400
        results = services.submit_request(g.s, tax_codes, types, d_from, d_to, now(), force=bool(j.get("force")),
                                          created_by=request.remote_addr or "")
        n_run = sum(1 for r in results if not r.skipped)
        return jsonify(results=[ser.submission_dict(r) for r in results], queued=n_run, skipped=len(results) - n_run)

    @app.post("/api/crawl/preview")
    def crawl_preview():
        """Kiểm tra trước (không tạo job): với mỗi (MST, loại) đã có trong database chưa."""
        j = request.get_json(silent=True) or {}
        tax_codes, invalid = services.parse_tax_codes(j.get("tax_codes", ""))
        types = [t for t in j.get("types", []) if t == "ALL" or t in TYPES]
        types = list(TYPES) if "ALL" in types else types
        d_from, d_to = parse_iso(j.get("date_from")), parse_iso(j.get("date_to"))
        if d_from and d_to and d_from > d_to:
            return jsonify(error="'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'."), 400
        out = []
        for tax in tax_codes[:50]:
            for typ in types:
                plan = services.plan_for(g.s, tax, typ, d_from, d_to, now(), force=bool(j.get("force")))
                out.append({"tax_code": tax, "ann_type": typ, "status": plan.status,
                            "needs_crawl": plan.needs_crawl, "message": coverage.describe(plan)})
        return jsonify(items=out, invalid=invalid, truncated=len(tax_codes) > 50)

    # ------------------------------------------------------------ crawl hàng loạt từ file Excel
    @app.get("/api/crawl/template.xlsx")
    def crawl_template():
        return send_file(io.BytesIO(bulk.make_template()), as_attachment=True,
                         download_name="egazette_mau_crawl.xlsx", mimetype=XLSX)

    @app.post("/api/crawl/import")
    def crawl_import():
        """Đọc file Excel và cho xem trước từng dòng: có hợp lệ không, đã có trong database chưa. KHÔNG tạo job."""
        f = request.files.get("file")
        if f is None or not f.filename:
            return jsonify(error="Chưa chọn file."), 400
        try:
            rows = bulk.parse_workbook(io.BytesIO(f.read()))
        except bulk.BulkError as e:
            return jsonify(error=str(e)), 400
        t = now()
        out, run, skip = [], 0, 0
        for r in rows:
            d = r.to_dict()
            d["pairs"] = []
            if r.ok and not r.warnings:          # dòng trùng với dòng trước chỉ báo cảnh báo, không tính vào số cần crawl
                for typ in r.types:
                    plan = services.plan_for(g.s, r.tax_code, typ, r.date_from, r.date_to, t, force=r.force)
                    d["pairs"].append({"ann_type": typ, "status": plan.status, "needs_crawl": plan.needs_crawl,
                                       "message": coverage.describe(plan)})
            d["to_run"] = sum(1 for p in d["pairs"] if p["needs_crawl"])
            d["to_skip"] = len(d["pairs"]) - d["to_run"]
            run, skip = run + d["to_run"], skip + d["to_skip"]
            out.append(d)
        valid = sum(1 for r in rows if r.ok)
        return jsonify(filename=f.filename, rows=out,
                       totals={"rows": len(rows), "valid": valid, "invalid": len(rows) - valid, "to_run": run,
                               "to_skip": skip})

    @app.post("/api/crawl/batch")
    def crawl_batch():
        """Tạo job cho các dòng đã xem trước. Kiểm tra lại toàn bộ ở server (không tin dữ liệu từ trình duyệt)."""
        j = request.get_json(silent=True) or {}
        items = j.get("rows")
        if not isinstance(items, list) or not items:
            return jsonify(error="Không có dòng nào để crawl."), 400
        if len(items) > bulk.MAX_ROWS:
            return jsonify(error=f"Tối đa {bulk.MAX_ROWS} dòng mỗi lần."), 400
        parsed, errors, pairs = [], [], 0
        for n, it in enumerate(items, 1):
            it = it if isinstance(it, dict) else {}
            ok, bad = services.parse_tax_codes(str(it.get("tax_code", "")))
            types = [t for t in (it.get("types") or []) if t in TYPES] if isinstance(it.get("types"), list) else []
            d_from, d_to = parse_iso(it.get("date_from")), parse_iso(it.get("date_to"))
            if len(ok) != 1 or bad:
                errors.append(f"Dòng {n}: mã số thuế không hợp lệ.")
            elif not types:
                errors.append(f"Dòng {n}: loại công bố không hợp lệ.")
            elif d_from and d_to and d_from > d_to:
                errors.append(f"Dòng {n}: 'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")
            else:
                parsed.append((ok[0], list(dict.fromkeys(types)), d_from, d_to, bool(it.get("force"))))
                pairs += len(parsed[-1][1])
        if not errors and pairs > bulk.MAX_PAIRS:
            errors.append(f"Vượt giới hạn {bulk.MAX_PAIRS} cặp (MST × loại công bố) mỗi lần gửi.")
        if errors:
            return jsonify(error=errors[0], errors=errors[:20]), 400
        results = []
        for tax, types, d_from, d_to, force in parsed:       # từng dòng một: mỗi dòng có khoảng ngày riêng
            results += services.submit_request(g.s, [tax], types, d_from, d_to, now(), force=force,
                                               created_by=request.remote_addr or "")
        n_run = sum(1 for r in results if not r.skipped)
        return jsonify(results=[ser.submission_dict(r) for r in results], queued=n_run, skipped=len(results) - n_run)

    # ------------------------------------------------------------ jobs
    @app.get("/api/jobs")
    def jobs():
        status = request.args.get("status", "")
        q = select(CrawlJob).order_by(CrawlJob.id.desc())
        if status:
            q = q.where(CrawlJob.status == status)
        page, per = page_arg(), per_page_arg()
        total = g.s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = g.s.execute(q.limit(per).offset((page - 1) * per)).scalars().all()
        return jsonify(paged([ser.job_dict(j) for j in items], total, page, per))

    @app.get("/api/jobs/<int:job_id>")
    def job_detail(job_id):
        job = g.s.get(CrawlJob, job_id) or abort(404)
        return jsonify(ser.job_dict(job, with_log=True))

    @app.post("/api/jobs/<int:job_id>/cancel")
    def job_cancel(job_id):
        job = g.s.get(CrawlJob, job_id) or abort(404)
        if job.status in (QUEUED, PAUSED):
            job.status, job.message, job.finished_at = CANCELLED, "Đã huỷ trước khi chạy", now()
            g.s.commit()
        elif job.status == RUNNING and app.worker:
            app.worker.cancel(job_id)
        g.s.refresh(job)
        return jsonify(ser.job_dict(job, with_log=True))

    @app.post("/api/jobs/<int:job_id>/retry")
    def job_retry(job_id):
        job = g.s.get(CrawlJob, job_id) or abort(404)
        res = services.submit_request(g.s, [job.tax_code], [job.ann_type], job.req_from, job.req_to, now(),
                                      force=job.force, created_by=request.remote_addr or "")
        return jsonify(ser.job_dict(res[0].job, with_log=True))

    # ------------------------------------------------------------ tìm kiếm
    @app.get("/api/search")
    def search():
        page, per = page_arg(), per_page_arg()
        items, total = services.search_announcements(g.s, search_filters(), page, per)
        return jsonify(paged([ser.announcement_summary(a) for a in items], total, page, per))

    @app.get("/api/search/export.xlsx")
    def search_export():
        items = services.all_announcements(g.s, search_filters())
        wb = Workbook()
        ws = wb.active
        ws.title = "Bố cáo"
        ws.append(["MST tra cứu", "Loại công bố", "Ngày giờ đăng", "Tiêu đề", "Tên doanh nghiệp", "MST trên bố cáo",
                   "Ngày thành lập", "Địa chỉ trụ sở chính", "Vốn điều lệ", "Ngày cấp ĐK thay đổi", "Nơi đăng ký",
                   "Người đại diện", "Số CCCD/CMND", "Trạng thái PDF", "Trạng thái tách", "File PDF (MinIO)"])
        wr = wb.create_sheet("Người đại diện")
        wr.append(["MST tra cứu", "Ngày giờ đăng", "Họ và tên", "Giới tính", "Chức danh", "Ngày sinh", "Dân tộc",
                   "Quốc tịch", "Loại giấy tờ", "Số giấy tờ", "Ngày cấp", "Nơi cấp", "Địa chỉ thường trú",
                   "Địa chỉ liên lạc"])
        for a in items:
            ws.append([a.tax_code, f"{a.ann_type} - {TYPES.get(a.ann_type, '')}", a.posted_at, a.title,
                       a.company_name, a.doc_tax_code, a.established_date, a.hq_address, a.charter_capital,
                       a.reg_change_date, a.reg_place, "\n".join(r.full_name for r in a.reps),
                       "\n".join(r.id_number for r in a.reps), a.pdf_status, a.parse_status,
                       location(a.pdf_bucket, a.pdf_path)])
            for r in a.reps:
                wr.append([a.tax_code, a.posted_at, r.full_name, r.gender, r.position, r.birth_date, r.ethnicity,
                           r.nationality, r.id_doc_type, r.id_number, r.id_issue_date, r.id_issue_place,
                           r.residence_address, r.contact_address])
        for sheet in (ws, wr):
            for c in sheet[1]:
                c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
                c.alignment = Alignment(wrap_text=True, vertical="center")
            for i in range(1, sheet.max_column + 1):
                sheet.column_dimensions[get_column_letter(i)].width = 22
            sheet.freeze_panes = "A2"
        for row in ws.iter_rows(min_row=2):
            row[2].number_format = "dd/mm/yyyy hh:mm:ss"
            for i in (6, 9):
                row[i].number_format = "dd/mm/yyyy"
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"bocao_{now():%Y%m%d_%H%M%S}.xlsx", mimetype=XLSX)

    @app.get("/api/announcements/<int:ann_id>")
    def announcement(ann_id):
        a = g.s.get(Announcement, ann_id) or abort(404)
        return jsonify(ser.announcement_detail(a))

    @app.get("/api/files/<int:ann_id>")
    def file_view(ann_id):
        """Stream PDF từ MinIO qua backend (giữ đăng nhập, không lộ địa chỉ/khoá MinIO ra trình duyệt).
        Bucket + key lấy từ database của chính bố cáo, không nhận đường dẫn từ người dùng."""
        a = g.s.get(Announcement, ann_id) or abort(404)
        if not (a.pdf_bucket and a.pdf_path):
            return jsonify(error="Bố cáo này chưa có file PDF trên MinIO."), 404
        try:
            size, chunks = get_store().open(a.pdf_path, a.pdf_bucket)
        except FileNotFoundError:
            return jsonify(error="Không tìm thấy file PDF trên MinIO (có thể đã bị xoá)."), 404
        except StoreError as e:
            return jsonify(error=f"Không đọc được file từ MinIO: {e}"), 502
        name = f"{a.tax_code}_{a.ann_type}_{a.posted_at:%Y%m%d_%H%M%S}.pdf"
        disp = "attachment" if request.args.get("download") == "1" else "inline"
        return Response(chunks, mimetype="application/pdf", headers={
            "Content-Length": str(size), "Content-Disposition": f'{disp}; filename="{name}"',
            "Cache-Control": "private, max-age=300"})

    # ------------------------------------------------------------ doanh nghiệp / người đại diện
    @app.get("/api/companies")
    def companies():
        page, per = page_arg(), per_page_arg()
        items, total = services.search_companies(g.s, search_filters(), page, per)
        return jsonify(paged([ser.company_row(c) for c in items], total, page, per))

    @app.get("/api/companies/<tax>")
    def company(tax):
        anns = g.s.execute(select(Announcement).where(Announcement.tax_code == tax)
                           .order_by(Announcement.posted_at.desc())).scalars().all()
        if not anns:
            abort(404)
        latest = ser.announcement_summary(anns[0])
        return jsonify(tax_code=tax, latest=latest, announcements=[ser.announcement_summary(a) for a in anns],
                       coverage=[ser.coverage_dict(c) for c in services.company_coverage(g.s, tax, now())])

    @app.get("/api/people")
    def people():
        page, per = page_arg(), per_page_arg()
        f = {"name": request.args.get("name", ""), "id_number": request.args.get("id_number", ""),
             "tax_code": request.args.get("tax_code", "")}
        rows, total = services.search_people(g.s, f, page, per)
        return jsonify(paged([ser.person_dict(r, a) for r, a in rows], total, page, per))

    # ------------------------------------------------------------ giao diện React đã build (nếu có)
    dist = config.FRONTEND_DIST

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path):
        if path.startswith("api/"):
            abort(404)
        if not (dist / "index.html").is_file():
            return jsonify(message="Egazette API đang chạy. Giao diện: chạy `npm run dev` trong thư mục frontend "
                                   "(hoặc `npm run build` để backend phục vụ luôn).", api="/api/meta")
        target = (dist / path).resolve()
        if path and dist.resolve() in target.parents and target.is_file():
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")       # React Router xử lý đường dẫn

    return app
