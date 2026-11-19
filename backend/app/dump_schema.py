"""In DDL MySQL của các bảng:  python -m app.dump_schema > schema.sql"""
import sys

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from .models import Base


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print("-- Egazette: schema MySQL 8 (utf8mb4). Ứng dụng tự tạo bảng khi khởi động (AUTO_CREATE_TABLES=true);")
    print("-- file này để tham khảo hoặc chạy tay.")
    print("-- Database tạo từ bản trước khi dùng MinIO: ứng dụng tự thêm 2 cột bên dưới khi khởi động; chạy tay thì:")
    print("--   ALTER TABLE announcements ADD COLUMN pdf_bucket VARCHAR(100) NOT NULL DEFAULT '';")
    print("--   ALTER TABLE announcements ADD COLUMN pdf_size INT NOT NULL DEFAULT 0;")
    print("-- Sau đó chạy `python -m app.migrate_pdfs` để đưa PDF cũ trên đĩa lên MinIO.\n")
    for table in Base.metadata.sorted_tables:
        print(str(CreateTable(table).compile(dialect=mysql.dialect())).strip() + ";\n")
        for ix in table.indexes:
            print(str(CreateIndex(ix).compile(dialect=mysql.dialect())).strip() + ";")
        print()


if __name__ == "__main__":
    main()
