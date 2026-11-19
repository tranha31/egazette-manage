"""
Nhập dữ liệu đã crawl bằng tool Excel cũ (egazette_auto.py) vào database.

    python -m app.import_excel ../egazette/output/ketqua_20261111_114428.xlsx
    python -m app.import_excel ketqua.xlsx --pdf-root ../egazette/output

- Sheet "Kết quả"  -> bảng announcements (+ upload PDF lên MinIO và tách nội dung nếu tìm thấy file theo cột "File PDF")
- Sheet "Nhật ký"  -> khoảng đã crawl (chỉ lấy các lần có kết quả, trạng thái OK).
  Lần "KHÔNG CÓ KẾT QUẢ" bị bỏ qua vì tool cũ không phân biệt được "không có bố cáo" với "captcha sai".
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select

from . import services
from .coverage import FLOOR
from .db import Session, create_tables, init_engine, now
from .models import CrawlCoverage
from .pdf_parser import parse_pdf
from .storage import StoreError, get_store


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M:%S")
    return str(v).strip()


def _rows(ws):
    head = [_cell(c.value) for c in ws[1]]
    for r in ws.iter_rows(min_row=2, values_only=True):
        if any(v not in (None, "") for v in r):
            yield dict(zip(head, r))


def import_excel(xlsx, pdf_root, session, log=print):
    wb = load_workbook(xlsx, data_only=True)
    stats = {"announcements": 0, "new": 0, "pdf": 0, "parsed": 0, "coverage": 0, "skipped": 0}
    when_now = now()

    if "Kết quả" in wb.sheetnames:
        for r in _rows(wb["Kết quả"]):
            tax = _cell(r.get("Mã số thuế tra cứu"))
            typ = _cell(r.get("Loại công bố")).split(" - ")[0].strip()
            label = _cell(r.get("Ngày giờ đăng"))
            if not (tax and typ and label):
                stats["skipped"] += 1
                continue
            info = {"time": f"{label} {_cell(r.get('Tiêu đề'))}".strip(),
                    "start": _cell(r.get("Ngày bắt đầu")), "end": _cell(r.get("Ngày kết thúc")),
                    "name_code": f"{_cell(r.get('Tên doanh nghiệp'))} MÃ SỐ DN: {_cell(r.get('MST trên bố cáo'))}",
                    "place": _cell(r.get("Nơi đặt trụ sở")), "type": _cell(r.get("Nội dung thay đổi"))}
            try:
                ann, created = services.upsert_announcement(session, tax, typ, info, None, when_now)
            except ValueError as e:
                log(f"  bỏ qua dòng ({tax} {typ}): {e}")
                stats["skipped"] += 1
                continue
            stats["announcements"] += 1
            stats["new"] += created
            rel_src = _cell(r.get("File PDF"))
            src = Path(pdf_root) / rel_src if rel_src else None
            if src and src.is_file():
                key = services.storage_rel(tax, typ, ann.posted_at)
                store = get_store()
                if not store.exists(key):
                    store.put_file(key, src)          # upload thẳng từ file nguồn lên MinIO
                ann.pdf_bucket, ann.pdf_path, ann.pdf_size, ann.pdf_status = store.bucket, key, src.stat().st_size, "ok"
                stats["pdf"] += 1
                if created or ann.parse_status != "ok":
                    services.apply_parse(session, ann, parse_pdf(src))
                    stats["parsed"] += ann.parse_status == "ok"
            elif not ann.pdf_status:
                ann.pdf_status = "none"
            session.commit()

    if "Nhật ký" in wb.sheetnames:
        for r in _rows(wb["Nhật ký"]):
            if _cell(r.get("Trạng thái")) != "OK":
                continue
            tax, typ = _cell(r.get("Mã số thuế")), _cell(r.get("Loại công bố"))
            at = _cell(r.get("Thời điểm"))
            m = re.match(r"(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})", at)
            if not (tax and typ and m):
                continue
            crawled_at = datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5]), int(m[6]))
            d_from, d_to = services.parse_vn_date(_cell(r.get("Từ ngày"))), services.parse_vn_date(_cell(r.get("Đến ngày")))
            d_from, d_to = d_from or FLOOR, d_to or crawled_at.date()
            exists = session.execute(select(CrawlCoverage.id).where(
                CrawlCoverage.tax_code == tax, CrawlCoverage.ann_type == typ, CrawlCoverage.date_from == d_from,
                CrawlCoverage.date_to == d_to, CrawlCoverage.crawled_at == crawled_at)).first()
            if not exists:
                session.add(CrawlCoverage(tax_code=tax, ann_type=typ, date_from=d_from, date_to=d_to,
                                          crawled_at=crawled_at, result_count=int(r.get("Số kết quả") or 0)))
                stats["coverage"] += 1
        session.commit()
    return stats


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xlsx", nargs="+", help="file ketqua_*.xlsx do tool Excel cũ tạo ra")
    ap.add_argument("--pdf-root", help="thư mục chứa 'pdf/<MST>/<LOẠI>/...' (mặc định: thư mục của file xlsx)")
    a = ap.parse_args()
    init_engine()
    create_tables()
    try:
        get_store().ensure_bucket()
    except StoreError as e:
        sys.exit(f"Không kết nối được MinIO, chưa thể upload PDF: {e}")
    for f in a.xlsx:
        with Session() as s:
            st = import_excel(f, a.pdf_root or Path(f).resolve().parent, s)
        print(f"{f}: {st}")


if __name__ == "__main__":
    main()
