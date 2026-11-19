"""Crawl hàng loạt từ file Excel: tạo file mẫu và đọc / kiểm tra file người dùng tải lên.

Định dạng giống tool Excel cũ (sheet "Input"): Mã số thuế | Loại công bố | Từ ngày | Đến ngày, thêm cột "Crawl lại".
Module này không đụng database; việc kiểm tra "đã có trong database chưa" nằm ở web.py / services.py.
"""
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.datavalidation import DataValidation

from .models import TYPES
from .services import parse_tax_codes

SHEET = "Input"
HEADERS = ["Mã số thuế", "Loại công bố", "Từ ngày", "Đến ngày", "Crawl lại"]
MAX_ROWS = 500          # số dòng dữ liệu tối đa mỗi file
MAX_PAIRS = 1000        # số cặp (MST × loại công bố) tối đa mỗi lần gửi: mỗi cặp tốn một lượt captcha
MAX_SCAN = 5000         # số dòng tối đa đọc từ file (chặn file có hàng triệu dòng trống)
HEADER_SEARCH_ROWS = 5  # cho phép vài dòng tiêu đề / ghi chú phía trên hàng tên cột

ALIASES = {
    "tax": ("mã số thuế", "mst", "ma so thue"),
    "type": ("loại công bố", "loai cong bo", "loại"),
    "from": ("từ ngày", "tu ngay"),
    "to": ("đến ngày", "den ngay"),
    "force": ("crawl lại", "bắt buộc crawl lại", "crawl lai"),
}
YES = {"có", "co", "x", "1", "true", "yes", "y", "đúng"}
NO = {"", "không", "khong", "0", "false", "no", "n"}
ALL_WORDS = {"ALL", "TẤT CẢ", "TAT CA"}


class BulkError(Exception):
    """Lỗi của cả file (không đọc được, thiếu cột, quá nhiều dòng...), khác với lỗi của từng dòng."""


@dataclass
class BulkRow:
    line: int                      # số dòng trong file Excel (để người dùng tìm lại)
    tax_code: str = ""
    types: list = field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    force: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def to_dict(self):
        return {"line": self.line, "tax_code": self.tax_code, "types": self.types,
                "date_from": self.date_from.isoformat() if self.date_from else None,
                "date_to": self.date_to.isoformat() if self.date_to else None,
                "force": self.force, "errors": self.errors, "warnings": self.warnings}


# ------------------------------------------------------------------ file mẫu
def make_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(HEADERS)
    ws.append(["0101243150", "AMEND", "01/01/2024", "31/12/2024", "Không"])      # dòng mẫu: MISA
    ws.append(["0100109106", "ALL", None, None, None])                           # mẫu: tất cả loại, không lọc ngày
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(vertical="center")
    for col, w in zip("ABCDE", (18, 18, 14, 14, 12)):
        ws.column_dimensions[col].width = w
    for r in range(2, MAX_ROWS + 2):             # MST và ngày là ô văn bản để Excel không ăn mất số 0 đầu
        for col in "ACD":
            ws[f"{col}{r}"].number_format = "@"
    types_dv = DataValidation(type="list", formula1='"ALL,' + ",".join(TYPES) + '"', allow_blank=True)
    force_dv = DataValidation(type="list", formula1='"Có,Không"', allow_blank=True)
    ws.add_data_validation(types_dv)
    ws.add_data_validation(force_dv)
    types_dv.add(f"B2:B{MAX_ROWS + 1}")
    force_dv.add(f"E2:E{MAX_ROWS + 1}")
    ws.freeze_panes = "A2"

    g = wb.create_sheet("Hướng dẫn")
    rows = [
        ["Cột", "Ý nghĩa"],
        ["Mã số thuế", "Bắt buộc. 10 hoặc 13 số (vd 0101243150 hoặc 0101243150-001), mỗi dòng một mã."],
        ["Loại công bố", "Bắt buộc. Một hoặc nhiều mã trong bảng bên dưới (ngăn cách bằng dấu phẩy, vd AMEND,NEW), "
                         "hoặc ALL để tra tất cả loại. Mỗi (MST × loại) tốn một lượt giải captcha."],
        ["Từ ngày / Đến ngày", "Tuỳ chọn, dạng dd/MM/yyyy. Bỏ trống cả hai = tất cả từ trước đến nay. "
                               "Hệ thống chỉ crawl phần chưa có trong database."],
        ["Crawl lại", "Tuỳ chọn. Điền \"Có\" để bỏ qua kiểm tra database và crawl lại đúng khoảng đã nhập."],
        [],
        ["Lưu ý", "Hai dòng mẫu trong sheet Input chỉ để tham khảo, hãy xoá hoặc thay bằng dữ liệu của bạn. "
                  f"Tối đa {MAX_ROWS} dòng và {MAX_PAIRS} cặp (MST × loại) mỗi lần."],
        [],
        ["Mã loại", "Tên loại công bố"],
    ] + [[k, v] for k, v in TYPES.items()]
    for row in rows:
        g.append(row)
    for r in (1, 8):
        for c in g[r]:
            c.font = Font(bold=True)
    for row in g.iter_rows(min_row=1, max_row=g.max_row):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    g.column_dimensions["A"].width = 22
    g.column_dimensions["B"].width = 100
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ đọc file
def _norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().strip("*:").strip().casefold()


def _text(v):
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _parse_date(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", s)
        if not m:
            raise ValueError
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    return date(y, mo, d)        # ValueError nếu ngày không tồn tại (vd 31/02)


def _parse_types(raw):
    """'AMEND, NEW' / 'Đăng ký mới' / 'ALL' -> ('...', [mã], lỗi|None)."""
    names = {v.casefold(): k for k, v in TYPES.items()}
    out, bad = [], []
    for tok in [t.strip() for t in re.split(r"[,;\n]+", raw) if t.strip()]:
        up = tok.upper()
        if up in ALL_WORDS:
            out.extend(TYPES)
        elif up in TYPES:
            out.append(up)
        elif tok.casefold() in names:
            out.append(names[tok.casefold()])
        else:
            bad.append(tok)
    return list(dict.fromkeys(out)), bad


def _parse_row(line, cells):
    row = BulkRow(line=line)
    raw_tax = cells["tax"]
    tax = _text(raw_tax)
    if isinstance(raw_tax, (int, float)) and tax.isdigit() and len(tax) == 9:
        tax = tax.zfill(10)                      # ô kiểu số: Excel đã ăn mất số 0 đầu
    ok, bad = parse_tax_codes(tax)
    if len(ok) == 1 and not bad:
        row.tax_code = ok[0]
    else:
        row.tax_code = tax
        row.errors.append("Mỗi dòng chỉ một mã số thuế." if len(ok) + len(bad) > 1 else
                          "Thiếu mã số thuế." if not tax else
                          f"Mã số thuế không hợp lệ: '{tax}' (cần 10 hoặc 13 số).")

    raw_type = _text(cells["type"])
    if not raw_type:
        row.errors.append("Thiếu loại công bố.")
    else:
        row.types, bad_types = _parse_types(raw_type)
        if bad_types:
            row.errors.append("Loại công bố không hợp lệ: " + ", ".join(f"'{b}'" for b in bad_types) + ".")

    for key, attr, label in (("from", "date_from", "Từ ngày"), ("to", "date_to", "Đến ngày")):
        try:
            setattr(row, attr, _parse_date(cells[key]))
        except ValueError:
            row.errors.append(f"{label} phải có dạng dd/MM/yyyy (đang là '{_text(cells[key])}').")
    if row.date_from and row.date_to and row.date_from > row.date_to:
        row.errors.append("'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")

    f = _text(cells["force"]).casefold()
    if f in YES:
        row.force = True
    elif f not in NO:
        row.errors.append(f"Cột Crawl lại chỉ nhận 'Có' hoặc 'Không' (đang là '{_text(cells['force'])}').")
    return row


def parse_workbook(stream) -> list:
    """Đọc file Excel người dùng tải lên -> danh sách BulkRow (cả dòng lỗi, để báo cho người dùng). Lỗi cả file -> BulkError."""
    try:
        wb = load_workbook(stream, read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError):
        raise BulkError("Không đọc được file. Hãy dùng file Excel .xlsx (tải file mẫu ở bước 1).") from None
    try:
        ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        col, header_line = {}, 0
        for n, cells in enumerate(it, start=1):
            if n > HEADER_SEARCH_ROWS:
                break
            heads = {_norm(c): i for i, c in enumerate(cells) if c is not None}
            found = {k: next((heads[a] for a in names if a in heads), None) for k, names in ALIASES.items()}
            if found["tax"] is not None and found["type"] is not None:
                col, header_line = found, n
                break
        if not col:
            raise BulkError("Không tìm thấy hàng tiêu đề. File cần có hai cột “Mã số thuế” và “Loại công bố” "
                            "(tải file mẫu để xem đúng định dạng).")

        rows, seen = [], {}
        for n, cells in enumerate(it, start=header_line + 1):
            if n - header_line > MAX_SCAN:
                raise BulkError(f"File có quá nhiều dòng (đọc tới dòng {MAX_SCAN} vẫn chưa hết).")
            get = lambda k: cells[col[k]] if col[k] is not None and col[k] < len(cells) else None  # noqa: E731
            data = {k: get(k) for k in ALIASES}
            if not any(_text(v) for v in data.values()):
                continue                         # dòng trống
            row = _parse_row(n, data)
            if row.ok:
                key = (row.tax_code, tuple(row.types), row.date_from, row.date_to, row.force)
                if key in seen:
                    row.warnings.append(f"Trùng với dòng {seen[key]}, sẽ bị bỏ qua khi crawl.")
                else:
                    seen[key] = n
            rows.append(row)
            if len(rows) > MAX_ROWS:
                raise BulkError(f"File có quá {MAX_ROWS} dòng. Hãy chia nhỏ file rồi tải lên từng phần.")
    finally:
        wb.close()
    if not rows:
        raise BulkError("File không có dòng dữ liệu nào bên dưới hàng tiêu đề.")
    pairs = sum(len(r.types) for r in rows if r.ok)
    if pairs > MAX_PAIRS:
        raise BulkError(f"File có {pairs} cặp (MST × loại công bố), vượt giới hạn {MAX_PAIRS} cặp mỗi lần. "
                        "Hãy chia nhỏ file hoặc chọn bớt loại công bố.")
    return rows
