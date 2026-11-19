"""
Chuyển các PDF đang nằm trên đĩa (bản trước khi dùng MinIO) lên MinIO và cập nhật database.

    python -m app.migrate_pdfs                     # chuyển các bố cáo chưa có pdf_bucket
    python -m app.migrate_pdfs --dry-run           # chỉ báo cáo, không upload, không sửa database
    python -m app.migrate_pdfs --source D:\\duong\\dan\\storage
    python -m app.migrate_pdfs --delete-local      # xoá file cục bộ sau khi đã upload và kiểm tra đúng kích thước

Mỗi bố cáo có pdf_status = ok, pdf_path (đường dẫn tương đối, vd pdf/<MST>/<LOẠI>/xxx.pdf) nhưng pdf_bucket rỗng sẽ được:
upload lên MinIO với object key = pdf_path, rồi ghi pdf_bucket + pdf_size. Chạy lại nhiều lần an toàn (bỏ qua cái đã chuyển).
Không có file nguồn thì chỉ báo cáo, không đổi gì trong database.
"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from .config import Config
from .db import Session, create_tables, init_engine
from .models import Announcement
from .storage import StoreError, get_store


def migrate(session, source, store, dry_run=False, delete_local=False, log=print):
    stats = {"total": 0, "uploaded": 0, "already": 0, "missing": 0, "deleted": 0}
    source = Path(source).resolve()
    rows = session.execute(select(Announcement).where(
        Announcement.pdf_status == "ok", Announcement.pdf_path != "", Announcement.pdf_bucket == ""
    ).order_by(Announcement.id)).scalars().all()
    for a in rows:
        stats["total"] += 1
        src = (source / a.pdf_path).resolve()
        if source not in src.parents or not src.is_file():        # cũng chặn pdf_path trỏ ra ngoài thư mục nguồn
            stats["missing"] += 1
            log(f"  THIẾU  #{a.id} {a.pdf_path}: không có file trong {source}")
            continue
        size = src.stat().st_size
        if dry_run:
            log(f"  sẽ chuyển  #{a.id} {a.pdf_path} ({size} byte)")
            continue
        remote = store.stat(a.pdf_path)
        if remote == size:
            stats["already"] += 1
        else:
            store.put_file(a.pdf_path, src)
            if store.stat(a.pdf_path) != size:
                raise StoreError(f"Upload {a.pdf_path} xong nhưng kích thước trên MinIO không khớp ({size} byte)")
            stats["uploaded"] += 1
        a.pdf_bucket, a.pdf_size = store.bucket, size
        session.commit()
        log(f"  OK     #{a.id} {a.pdf_path} -> s3://{store.bucket}/{a.pdf_path}")
        if delete_local:
            src.unlink()
            stats["deleted"] += 1
    return stats


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(Config.LEGACY_STORAGE_DIR), help="thư mục chứa pdf/<MST>/<LOẠI>/... (mặc định LEGACY_STORAGE_DIR)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--delete-local", action="store_true")
    a = ap.parse_args()
    init_engine()
    create_tables()                    # thêm cột pdf_bucket / pdf_size nếu database còn là bản cũ
    store = None                       # dry-run chỉ đọc database + đĩa, không cần (và không chạm) MinIO
    if not a.dry_run:
        try:
            store = get_store()
            store.ensure_bucket()
        except StoreError as e:
            sys.exit(f"Không kết nối được MinIO: {e}")
    with Session() as s:
        st = migrate(s, a.source, store, a.dry_run, a.delete_local)
    print(("[dry-run] " if a.dry_run else "") + f"Kết quả: {st}")
    if st["missing"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
