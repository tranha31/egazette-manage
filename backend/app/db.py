"""Kết nối database (SQLAlchemy). Dùng MySQL; test có thể trỏ sang SQLite."""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import Config

_state = {"engine": None, "Session": None}


def init_engine(url=None):
    url = url or Config.DATABASE_URL
    kw = {"pool_pre_ping": True, "pool_recycle": 3600}
    if url.startswith("sqlite"):
        kw = {"connect_args": {"check_same_thread": False}}
    engine = create_engine(url, **kw)
    _state["engine"] = engine
    _state["Session"] = sessionmaker(engine, expire_on_commit=False)
    return engine


def engine():
    if _state["engine"] is None:
        init_engine()
    return _state["engine"]


def Session():
    if _state["Session"] is None:
        init_engine()
    return _state["Session"]()


def create_tables():
    from .models import Base
    Base.metadata.create_all(engine())
    migrate()


# Cột thêm sau khi bảng đã được tạo ở bản trước: (bảng, cột, định nghĩa). create_all không tự thêm cột vào bảng có sẵn.
_ADDED_COLUMNS = [
    ("announcements", "pdf_bucket", "VARCHAR(100) NOT NULL DEFAULT ''"),   # PDF chuyển sang MinIO
    ("announcements", "pdf_size", "INT NOT NULL DEFAULT 0"),
]


def migrate():
    """Thêm các cột còn thiếu vào bảng đã có (idempotent, chạy được trên MySQL và SQLite)."""
    from sqlalchemy import inspect, text
    eng = engine()
    insp = inspect(eng)
    for table, column, ddl in _ADDED_COLUMNS:
        if table in insp.get_table_names() and column not in {c["name"] for c in insp.get_columns(table)}:
            with eng.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def now():
    """Giờ hiện tại theo múi giờ cấu hình (naive, lưu thẳng vào DATETIME)."""
    return datetime.now(ZoneInfo(Config.APP_TZ)).replace(tzinfo=None, microsecond=0)
