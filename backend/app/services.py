"""Nghiệp vụ: đặt yêu cầu crawl (kiểm tra đã có chưa), lưu bố cáo, tìm kiếm."""
import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import exists, func, or_, select, tuple_

from . import coverage as cov
from .config import Config
from .models import (PENDING_STATUSES, QUEUED, SKIPPED, TYPES, Announcement, AnnouncementField, CrawlCoverage,
                     CrawlJob, LegalRep)

TAX_RE = re.compile(r"^\d{10}(-\d{3})?$")


# ------------------------------------------------------------------ parse giá trị
def parse_vn_date(s):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_posted(label):
    """'12/05/2026 5:06:00 CH ...' -> datetime(2026,5,12,17,6,0). SA = sáng, CH = chiều."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(SA|CH)?", label or "")
    if not m:
        return None
    d, mo, y, h, mi, s, ap = int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]), m[7]
    if ap == "CH" and h < 12:
        h += 12
    elif ap == "SA" and h == 12:
        h = 0
    try:
        return datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None


def split_label(label):
    """'12/05/2026 5:06:00 CH Đăng ký thay đổi' -> ('12/05/2026 5:06:00 CH', 'Đăng ký thay đổi')."""
    m = re.match(r"(\d{2}/\d{2}/\d{4} \d{1,2}:\d{2}:\d{2}\s*(?:SA|CH)?)\s*(.*)", label or "")
    return (m.group(1), m.group(2)) if m else (label or "", "")


def split_name_code(s):
    m = re.match(r"(.*?)\s*MÃ SỐ DN:\s*(\S+)", s or "", re.S)
    return (re.sub(r"\s+", " ", m.group(1)).strip(), m.group(2)) if m else (re.sub(r"\s+", " ", s or "").strip(), "")


def parse_tax_codes(text):
    """Tách danh sách MST (cách nhau bởi dấu cách, xuống dòng, ',' ';'). Trả về (hợp lệ, không hợp lệ)."""
    ok, bad = [], []
    for tok in re.split(r"[\s,;]+", text or ""):
        tok = tok.strip()
        if not tok:
            continue
        if tok.isdigit() and len(tok) == 9:
            tok = tok.zfill(10)  # dán từ Excel hay mất số 0 đầu của MST 10 số
        if TAX_RE.match(tok):
            if tok not in ok:
                ok.append(tok)
        else:
            bad.append(tok)
    return ok, bad


def storage_rel(tax, typ, posted_at):
    return f"pdf/{tax}/{typ}/{tax}_{typ}_{posted_at:%Y%m%d_%H%M%S}.pdf"


# ------------------------------------------------------------------ đặt yêu cầu crawl
@dataclass
class Submission:
    tax_code: str
    ann_type: str
    plan: cov.Plan
    job: CrawlJob

    @property
    def skipped(self):
        return self.job.status == SKIPPED


def covered_records(session, tax, typ):
    rows = session.execute(select(CrawlCoverage.date_from, CrawlCoverage.date_to, CrawlCoverage.crawled_at)
                           .where(CrawlCoverage.tax_code == tax, CrawlCoverage.ann_type == typ)).all()
    return [(r[0], r[1], r[2]) for r in rows]


def pending_intervals(session, tax, typ):
    """Khoảng của các job đang chờ/đang chạy cùng (MST, loại): coi như sắp được phủ, tránh crawl trùng."""
    jobs = session.execute(select(CrawlJob).where(
        CrawlJob.tax_code == tax, CrawlJob.ann_type == typ, CrawlJob.status.in_(PENDING_STATUSES),
        CrawlJob.cover_from.is_not(None), CrawlJob.cover_to.is_not(None))).scalars().all()
    return [cov.Interval(j.cover_from, j.cover_to) for j in jobs]


def plan_for(session, tax, typ, d_from, d_to, now, force=False):
    return cov.make_plan(d_from, d_to, covered_records(session, tax, typ), pending_intervals(session, tax, typ),
                         now, Config.TODAY_RECHECK_MINUTES, force=force)


def submit_request(session, tax_codes, types, d_from, d_to, now, force=False, created_by=""):
    """
    Với mỗi (MST, loại): kiểm tra database đã có chưa.
      - đã có    -> ghi 1 job trạng thái 'skipped' (để lưu lịch sử), KHÔNG crawl
      - thiếu    -> tạo job 'queued' chỉ cho phần thiếu
    """
    if d_from and d_to and d_from > d_to:
        raise ValueError("'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")
    types = list(TYPES) if "ALL" in types else list(dict.fromkeys(types))
    out = []
    for tax in tax_codes:
        for typ in types:
            plan = plan_for(session, tax, typ, d_from, d_to, now, force)
            job = CrawlJob(tax_code=tax, ann_type=typ, req_from=d_from, req_to=d_to, force=force,
                           message=cov.describe(plan), created_by=created_by, created_at=now, log="")
            if plan.needs_crawl:
                job.status = QUEUED
                job.crawl_from, job.crawl_to = plan.site_from, plan.site_to
                job.cover_from, job.cover_to = plan.crawl.start, plan.crawl.end
            else:
                job.status = SKIPPED
                job.started_at = job.finished_at = now
            session.add(job)
            out.append(Submission(tax, typ, plan, job))
    session.commit()
    return out


# ------------------------------------------------------------------ lưu bố cáo
def _g(rows, key, group="Thông tin chung"):
    return next((r["value"] for r in rows if r["group"] == group and r["key"] == key), "")


def upsert_announcement(session, tax, typ, info, job_id, now):
    """info = dict một dòng kết quả: time, start, end, name_code, place, type. Trả về (announcement, created)."""
    posted = parse_posted(info["time"])
    if posted is None:
        raise ValueError(f"không đọc được ngày giờ đăng: {info['time']!r}")
    ann = session.execute(select(Announcement).where(
        Announcement.tax_code == tax, Announcement.ann_type == typ, Announcement.posted_at == posted)
    ).scalar_one_or_none()
    created = ann is None
    if created:
        ann = Announcement(tax_code=tax, ann_type=typ, posted_at=posted, posted_date=posted.date(),
                           created_at=now, pdf_status="", parse_status="")
        session.add(ann)
    _, title = split_label(info["time"])
    name, code = split_name_code(info.get("name_code", ""))
    ann.title = title[:255]
    ann.start_at, ann.end_at = (info.get("start") or "")[:40], (info.get("end") or "")[:40]
    ann.place, ann.change_type = (info.get("place") or "")[:255], (info.get("type") or "")[:255]
    if not ann.company_name:
        ann.company_name = name[:500]
    if not ann.doc_tax_code:
        ann.doc_tax_code = code[:20]
    ann.job_id, ann.updated_at = job_id, now
    session.flush()
    return ann, created


def apply_parse(session, ann, parsed):
    """Ghi kết quả tách PDF (pdf_parser.parse_pdf) vào announcement + bảng fields + reps."""
    if not parsed["ok"]:
        ann.parse_status = ("failed: " + parsed["error"])[:255]
        return
    rows = parsed["rows"]
    ann.company_name = (_g(rows, "Tên doanh nghiệp") or ann.company_name)[:500]
    ann.doc_tax_code = (_g(rows, "Mã số doanh nghiệp") or ann.doc_tax_code)[:20]
    ann.established_date = parse_vn_date(_g(rows, "Ngày thành lập"))
    ann.hq_address = _g(rows, "Địa chỉ trụ sở chính")
    ann.reg_change_date = parse_vn_date(_g(rows, "Ngày cấp đăng ký thay đổi"))
    ann.reg_place = _g(rows, "Nơi đăng ký")[:255]
    cap = next((r["value"] for r in rows if r["key"] == "Vốn điều lệ" and r["group"].startswith("[MỚI]")), "") \
        or next((r["value"] for r in rows if r["key"] == "Vốn điều lệ"), "")
    ann.charter_capital = cap[:80]

    ann.fields.clear()
    ann.reps.clear()
    session.flush()
    for i, r in enumerate(rows, 1):
        ann.fields.append(AnnouncementField(seq=i, grp=r["group"][:255], field_key=r["key"][:255],
                                            field_value=r["value"]))
    for i, p in enumerate(parsed["reps"], 1):
        ann.reps.append(LegalRep(
            seq=i, full_name=p.get("Họ và tên", "")[:255], gender=p.get("Giới tính", "")[:20],
            position=p.get("Chức danh", "")[:255], birth_date=parse_vn_date(p.get("Ngày sinh")),
            ethnicity=p.get("Dân tộc", "")[:80], nationality=p.get("Quốc tịch", "")[:80],
            id_doc_type=p.get("Loại giấy tờ", "")[:120], id_number=p.get("Số giấy tờ (CCCD/CMND)", "")[:40],
            id_issue_date=parse_vn_date(p.get("Ngày cấp")), id_issue_place=p.get("Nơi cấp", "")[:255],
            residence_address=p.get("Địa chỉ thường trú", ""), contact_address=p.get("Địa chỉ liên lạc", "")))
    ann.parse_status = "ok"


def record_coverage(session, job, count, now):
    """Ghi nhận khoảng đã crawl thành công (chỉ gọi khi crawl trọn vẹn)."""
    if job.cover_from and job.cover_to:
        session.add(CrawlCoverage(tax_code=job.tax_code, ann_type=job.ann_type, date_from=job.cover_from,
                                  date_to=job.cover_to, crawled_at=now, job_id=job.id, result_count=count))


# ------------------------------------------------------------------ tìm kiếm
def _like(q):
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def _prefix(q):
    """LIKE 'q%' (tìm theo đầu MST) có escape ký tự đặc biệt."""
    return _like(q.strip())[:-1] + "%"   # _like trả '%...%' -> bỏ '%' cuối rồi thêm lại sau chuỗi đã escape


def announcement_conditions(f):
    """f: dict q, deep, tax_code, ann_type, date_from, date_to, pdf_only."""
    c = []
    q = (f.get("q") or "").strip()
    if q:
        like = _like(q)
        parts = [Announcement.company_name.like(like, escape="\\"),
                 Announcement.tax_code.like(like, escape="\\"),
                 Announcement.doc_tax_code.like(like, escape="\\"),
                 Announcement.hq_address.like(like, escape="\\"),
                 exists().where(LegalRep.announcement_id == Announcement.id,
                                or_(LegalRep.full_name.like(like, escape="\\"),
                                    LegalRep.id_number.like(like, escape="\\")))]
        if f.get("deep"):
            parts.append(exists().where(AnnouncementField.announcement_id == Announcement.id,
                                        AnnouncementField.field_value.like(like, escape="\\")))
        c.append(or_(*parts))
    if (f.get("tax_code") or "").strip():
        c.append(Announcement.tax_code.like(_prefix(f["tax_code"]), escape="\\"))
    if f.get("ann_type"):
        c.append(Announcement.ann_type == f["ann_type"])
    if f.get("date_from"):
        c.append(Announcement.posted_date >= f["date_from"])
    if f.get("date_to"):
        c.append(Announcement.posted_date <= f["date_to"])
    if f.get("pdf_only"):
        c.append(Announcement.pdf_status == "ok")
    return c


def search_announcements(session, f, page=1, per_page=None):
    per_page = per_page or Config.PER_PAGE
    where = announcement_conditions(f)
    total = session.execute(select(func.count()).select_from(Announcement).where(*where)).scalar_one()
    items = session.execute(select(Announcement).where(*where).order_by(Announcement.posted_at.desc(), Announcement.id.desc())
                            .limit(per_page).offset((max(page, 1) - 1) * per_page)).scalars().all()
    return items, total


def all_announcements(session, f, limit=20000):
    where = announcement_conditions(f)
    return session.execute(select(Announcement).where(*where).order_by(Announcement.posted_at.desc())
                           .limit(limit)).scalars().all()


def search_companies(session, f, page=1, per_page=None):
    """Mỗi MST một dòng: thông tin lấy từ bố cáo mới nhất + số bố cáo."""
    per_page = per_page or Config.PER_PAGE
    where = announcement_conditions(f)
    agg = (select(Announcement.tax_code, func.count().label("n"), func.max(Announcement.posted_at).label("last_at"))
           .where(*where).group_by(Announcement.tax_code).subquery())
    total = session.execute(select(func.count()).select_from(agg)).scalar_one()
    rows = session.execute(select(agg).order_by(agg.c.last_at.desc()).limit(per_page)
                           .offset((max(page, 1) - 1) * per_page)).all()
    latest = {}
    if rows:
        pairs = [(r.tax_code, r.last_at) for r in rows]
        for a in session.execute(select(Announcement).where(
                tuple_(Announcement.tax_code, Announcement.posted_at).in_(pairs))).scalars():
            latest[a.tax_code] = a
    out = []
    for r in rows:
        a = latest.get(r.tax_code)
        out.append({"tax_code": r.tax_code, "count": r.n, "last_at": r.last_at, "latest": a,
                    "reps": ", ".join(p.full_name for p in a.reps) if a else ""})
    return out, total


def search_people(session, f, page=1, per_page=None):
    per_page = per_page or Config.PER_PAGE
    cond = []
    if (f.get("name") or "").strip():
        cond.append(LegalRep.full_name.like(_like(f["name"].strip()), escape="\\"))
    if (f.get("id_number") or "").strip():
        cond.append(LegalRep.id_number.like(_like(f["id_number"].strip()), escape="\\"))
    if (f.get("tax_code") or "").strip():
        cond.append(Announcement.tax_code.like(_prefix(f["tax_code"]), escape="\\"))
    base = select(LegalRep, Announcement).join(Announcement, LegalRep.announcement_id == Announcement.id).where(*cond)
    total = session.execute(select(func.count()).select_from(LegalRep)
                            .join(Announcement, LegalRep.announcement_id == Announcement.id).where(*cond)).scalar_one()
    rows = session.execute(base.order_by(Announcement.posted_at.desc(), LegalRep.seq)
                           .limit(per_page).offset((max(page, 1) - 1) * per_page)).all()
    return rows, total


def stats(session):
    return {
        "announcements": session.execute(select(func.count()).select_from(Announcement)).scalar_one(),
        "companies": session.execute(select(func.count(func.distinct(Announcement.tax_code)))).scalar_one(),
        "pdf_ok": session.execute(select(func.count()).select_from(Announcement)
                                  .where(Announcement.pdf_status == "ok")).scalar_one(),
        "queued": session.execute(select(func.count()).select_from(CrawlJob)
                                  .where(CrawlJob.status.in_(PENDING_STATUSES))).scalar_one(),
    }


def company_coverage(session, tax, now):
    """Các khoảng đã crawl của một MST, kèm khoảng hiệu lực thực tế."""
    rows = session.execute(select(CrawlCoverage).where(CrawlCoverage.tax_code == tax)
                           .order_by(CrawlCoverage.ann_type, CrawlCoverage.date_from)).scalars().all()
    out = []
    for r in rows:
        eff = cov.effective_interval(r.date_from, r.date_to, r.crawled_at, now, Config.TODAY_RECHECK_MINUTES)
        out.append({"row": r, "effective": eff})
    return out
