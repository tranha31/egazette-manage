"""Mô hình dữ liệu (MySQL, utf8mb4)."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

LongText = Text().with_variant(MEDIUMTEXT(), "mysql")  # nhật ký job có thể dài hơn 64KB
MYSQL = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci", "mysql_engine": "InnoDB"}

# Mã loại công bố = value của dropdown trên trang bố cáo
TYPES = {
    "NEW": "Đăng ký mới",
    "AMEND": "Đăng ký thay đổi",
    "CORP": "Giải thể",
    "COOP": "HTX, LHHTX, các ĐVTT và tổ hợp tác",
    "OTHER": "Loại khác",
    "CHANTC": "Thông báo thay đổi",
    "REVOKE": "Vi phạm/ Thu hồi",
}

# Trạng thái job
QUEUED, RUNNING, DONE, DONE_WARN, FAILED, PAUSED, SKIPPED, CANCELLED = (
    "queued", "running", "done", "done_warn", "failed", "paused", "skipped", "cancelled")
PENDING_STATUSES = (QUEUED, RUNNING, PAUSED)  # job chưa xong: coi như "đang giữ chỗ" khoảng thời gian của nó
STATUS_LABEL = {QUEUED: "Đang chờ", RUNNING: "Đang chạy", DONE: "Hoàn tất", DONE_WARN: "Xong (có lưu ý)",
                FAILED: "Lỗi", PAUSED: "Tạm dừng", SKIPPED: "Bỏ qua (đã có)", CANCELLED: "Đã huỷ"}
STATUS_CLASS = {QUEUED: "info", RUNNING: "info", DONE: "ok", DONE_WARN: "warn", FAILED: "bad", PAUSED: "warn",
                SKIPPED: "muted", CANCELLED: "muted"}


class Base(DeclarativeBase):
    pass


class CrawlJob(Base):
    """Một yêu cầu crawl cho (MST, loại công bố, khoảng thời gian). Cũng lưu cả yêu cầu bị bỏ qua vì đã có."""
    __tablename__ = "crawl_jobs"
    __table_args__ = (Index("ix_jobs_status", "status"), Index("ix_jobs_tax_type", "tax_code", "ann_type"), MYSQL)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_code: Mapped[str] = mapped_column(String(20))
    ann_type: Mapped[str] = mapped_column(String(10))
    req_from: Mapped[date | None] = mapped_column(Date, nullable=True)   # khoảng người dùng nhập
    req_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    crawl_from: Mapped[date | None] = mapped_column(Date, nullable=True)  # khoảng thực sự gửi lên trang (None = không lọc ngày)
    crawl_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    cover_from: Mapped[date | None] = mapped_column(Date, nullable=True)  # khoảng sẽ ghi nhận "đã phủ" khi crawl xong
    cover_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    force: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(12), default=QUEUED)
    message: Mapped[str] = mapped_column(Text, default="")
    log: Mapped[str] = mapped_column(LongText, default="")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    pdf_ok: Mapped[int] = mapped_column(Integer, default=0)
    pdf_fail: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CrawlCoverage(Base):
    """Khoảng thời gian đã crawl THÀNH CÔNG cho (MST, loại). Dùng để quyết định có cần crawl lại hay không."""
    __tablename__ = "crawl_coverage"
    __table_args__ = (Index("ix_cov_tax_type", "tax_code", "ann_type"), MYSQL)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_code: Mapped[str] = mapped_column(String(20))
    ann_type: Mapped[str] = mapped_column(String(10))
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    crawled_at: Mapped[datetime] = mapped_column(DateTime)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)


class Announcement(Base):
    """Một bố cáo (một dòng trong bảng kết quả + nội dung tách từ PDF)."""
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint("tax_code", "ann_type", "posted_at", name="uq_ann"),
        Index("ix_ann_posted_date", "posted_date"),
        Index("ix_ann_company", "company_name"),
        MYSQL,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tax_code: Mapped[str] = mapped_column(String(20))        # MST đã dùng để tra cứu
    ann_type: Mapped[str] = mapped_column(String(10))
    posted_at: Mapped[datetime] = mapped_column(DateTime)    # ngày giờ đăng
    posted_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(255), default="")
    start_at: Mapped[str] = mapped_column(String(40), default="")   # ngày bắt đầu / kết thúc hiển thị trên trang
    end_at: Mapped[str] = mapped_column(String(40), default="")
    place: Mapped[str] = mapped_column(String(255), default="")
    change_type: Mapped[str] = mapped_column(String(255), default="")
    # thông tin tách từ PDF
    company_name: Mapped[str] = mapped_column(String(500), default="")
    doc_tax_code: Mapped[str] = mapped_column(String(20), default="")
    established_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hq_address: Mapped[str] = mapped_column(Text, default="")
    charter_capital: Mapped[str] = mapped_column(String(80), default="")
    reg_change_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reg_place: Mapped[str] = mapped_column(String(255), default="")
    # file PDF trên MinIO: bucket + object key (vd egazette / pdf/0101243150/AMEND/0101243150_AMEND_20260512_170600.pdf)
    pdf_bucket: Mapped[str] = mapped_column(String(100), default="", server_default="")   # rỗng = chưa có file trên MinIO
    pdf_path: Mapped[str] = mapped_column(String(500), default="")   # object key trong bucket
    pdf_size: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))  # byte
    pdf_status: Mapped[str] = mapped_column(String(255), default="")  # ok | failed:<lý do> | none
    parse_status: Mapped[str] = mapped_column(String(255), default="")  # ok | failed:<lý do> | none
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    fields: Mapped[list["AnnouncementField"]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan", order_by="AnnouncementField.seq")
    reps: Mapped[list["LegalRep"]] = relationship(
        back_populates="announcement", cascade="all, delete-orphan", order_by="LegalRep.seq")


class AnnouncementField(Base):
    """Toàn bộ nội dung PDF dạng Nhóm - Khoá - Giá trị."""
    __tablename__ = "announcement_fields"
    __table_args__ = (Index("ix_fields_ann", "announcement_id", "seq"), MYSQL)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    grp: Mapped[str] = mapped_column(String(255))
    field_key: Mapped[str] = mapped_column(String(255))
    field_value: Mapped[str] = mapped_column(Text)
    announcement: Mapped[Announcement] = relationship(back_populates="fields")


class LegalRep(Base):
    """Người đại diện theo pháp luật (mục 5 của bố cáo)."""
    __tablename__ = "legal_reps"
    __table_args__ = (Index("ix_rep_ann", "announcement_id"), Index("ix_rep_name", "full_name"),
                      Index("ix_rep_idnum", "id_number"), MYSQL)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    gender: Mapped[str] = mapped_column(String(20), default="")
    position: Mapped[str] = mapped_column(String(255), default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ethnicity: Mapped[str] = mapped_column(String(80), default="")
    nationality: Mapped[str] = mapped_column(String(80), default="")
    id_doc_type: Mapped[str] = mapped_column(String(120), default="")
    id_number: Mapped[str] = mapped_column(String(40), default="")   # CCCD / CMND
    id_issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    id_issue_place: Mapped[str] = mapped_column(String(255), default="")
    residence_address: Mapped[str] = mapped_column(Text, default="")
    contact_address: Mapped[str] = mapped_column(Text, default="")
    announcement: Mapped[Announcement] = relationship(back_populates="reps")
