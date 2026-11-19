"""
Bóc tách thông tin trong PDF bố cáo (bocaodientu.dkkd.gov.vn) thành key - value.

Vì sao cần giải mã: PDF do Microsoft Reporting Services tạo, font Times New Roman nhúng dạng
Identity-H nhưng KHÔNG có bảng ToUnicode, nên chữ trích ra là số thứ tự glyph (rác, ví dụ
"&Ð1*7<&Ә3+Ҫ10,6$" thay cho "CÔNG TY CỔ PHẦN MISA"). Ta đổi glyph về Unicode bằng chính bảng
glyph của font Times New Roman trong Windows (C:\\Windows\\Fonts\\times*.ttf), nên máy chạy
cần là Windows (hoặc có sẵn 4 file font này, trỏ tới bằng biến môi trường PDF_FONT_DIR). Không cần OCR.
Phải là đúng font của Windows: font "tương thích" như Liberation Serif có số thứ tự glyph khác nên giải mã sai.

Dùng:
    from pdf_parser import parse_pdf
    r = parse_pdf("file.pdf")
    r["rows"]   # [{"group": ..., "key": ..., "value": ...}, ...]
    r["reps"]   # danh sách người đại diện theo pháp luật (dict)
    r["ok"], r["error"]

    python pdf_parser.py file.pdf     # in key - value ra màn hình
"""
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import pymupdf
from fontTools.ttLib import TTFont

FONT_FILES = {"": "times.ttf", "Bold": "timesbd.ttf", "Italic": "timesi.ttf", "BoldItalic": "timesbi.ttf"}


def font_dir():
    """Thư mục chứa 4 file font Times New Roman. Đặt PDF_FONT_DIR (vd /fonts khi chạy trong Docker/Linux);
    không đặt thì dùng thư mục Fonts của Windows."""
    custom = os.environ.get("PDF_FONT_DIR")
    return Path(custom) if custom else Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

NAME_WRAP_X = 435     # cột "Tên ngành": tên kết thúc từ x này trở đi là đã xuống dòng
RIGHT_MARGIN_X = 480 # dòng kết thúc ở bên phải mốc này coi là dòng bị xuống hàng (còn tiếp ở dòng sau)


# ------------------------------------------------------------------ giải mã glyph -> Unicode

@lru_cache(maxsize=None)
def _gid_to_char(style):
    path = font_dir() / FONT_FILES[style]
    if not path.exists():
        raise FileNotFoundError(f"Thiếu font {path}. Cần 4 file Times New Roman (times, timesbd, timesi, timesbi .ttf) "
                                "của Windows: dùng máy Windows hoặc đặt PDF_FONT_DIR trỏ tới thư mục chứa chúng.")
    font = TTFont(str(path))
    order = font.getGlyphOrder()
    inv = {}
    for uni, name in font.getBestCmap().items():
        inv.setdefault(order.index(name), chr(uni))
    return inv


def _style(fontname):
    if "Bold" in fontname and "Ital" in fontname:
        return "BoldItalic"
    if "Bold" in fontname:
        return "Bold"
    if "Ital" in fontname:
        return "Italic"
    return ""


def _span_text(span):
    text = span["text"]
    if span["font"].startswith("Times New Roman"):  # font Type0 Identity-H: ký tự là glyph ID
        inv = _gid_to_char(_style(span["font"]))
        # U+0020 là dấu cách do PyMuPDF tự chèn, dấu cách thật của font là glyph 3
        text = "".join("" if c == " " else inv.get(ord(c), "?") for c in text)
    return text


# ------------------------------------------------------------------ dựng lại từng dòng

def _page_lines(page, ytol=3.0):
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                t = _span_text(s).replace("\u00a0", " ")
                if t.strip():
                    x0, y0, x1, y1 = s["bbox"]
                    spans.append({"t": t, "x0": x0, "x1": x1, "yc": (y0 + y1) / 2})
    spans.sort(key=lambda s: (s["yc"], s["x0"]))
    rows = []
    for s in spans:
        if rows and abs(rows[-1][0]["yc"] - s["yc"]) <= ytol:
            rows[-1].append(s)
        else:
            rows.append([s])
    out = []
    for r in rows:
        r.sort(key=lambda s: s["x0"])
        txt, prev = "", None
        seg_x1 = []  # x1 của từng ô (đoạn cách nhau >= 12pt)
        for s in r:
            if prev is not None:
                gap = s["x0"] - prev["x1"]
                if gap >= 12:
                    seg_x1.append(prev["x1"])
                    txt += "   "  # khoảng cách lớn: ngăn giữa các ô / nhãn - giá trị
                elif (prev["t"].rstrip().endswith((":", "*"))
                      and not s["t"].startswith(" ") and not txt.endswith(" ")):
                    txt += " "
            txt += s["t"]
            prev = s
        seg_x1.append(prev["x1"])
        out.append({"text": txt.strip(), "x0": r[0]["x0"], "x1": max(s["x1"] for s in r), "seg_x1": seg_x1})
    return out


def read_lines(path):
    doc = pymupdf.open(str(path))
    try:
        return [ln for page in doc for ln in _page_lines(page)]
    finally:
        doc.close()


# ------------------------------------------------------------------ nhận diện cấu trúc

FOOTER_RE = re.compile(r"^(Thời gian đăng|Bố cáo/Thông báo này được đăng)")
PERIOD_RE = re.compile(r"từ ngày\s+(\d{2}/\d{2}/\d{4})\s+đến ngày\s+(\d{2}/\d{2}/\d{4})")
TOP_RE = re.compile(r"^([1-9])\.\s+(.+)$")
SUB_RE = re.compile(
    r"^(Thông tin (về )?[^:]{3,50}|Người đại diện[^:]{0,30}|Ngành,? nghề kinh doanh|Địa chỉ trụ sở chính"
    r"|Cổ đông[^:]{0,40}|Chủ sở hữu[^:]{0,30}|Thành viên[^:]{0,30}|Danh sách[^:]{0,40})\s*:?$")
NUM_RE = re.compile(r"^[\d.,%()\-\s]+$")

TOP_KEYS = [
    (r"^Tên (công ty|doanh nghiệp)", "ten"),
    (r"^Mã số doanh nghiệp", "mst"),
    (r"^Ngày (đăng ký )?thành lập", "ngay_tl"),
    (r"^Địa chỉ trụ sở chính", "dia_chi"),
    (r"^Người đại diện theo pháp luật", "reps"),
    (r"^Nội dung thay đổi", "change"),
    (r"^Ngày (cấp )?đăng ký thay đổi", "ngay_dk"),
    (r"^Nơi đăng ký", "noi_dk"),
    (r"^Ghi chú", "ghi_chu"),
]

# Tên nhãn khác nhau giữa mẫu cũ và mẫu mới -> một tên chuẩn
LABEL_MAP = [
    (r"^Họ (và )?tên", "Họ và tên"),
    (r"^(Sinh ngày|Ngày sinh)", "Ngày sinh"),
    (r"^Giới tính", "Giới tính"),
    (r"^Chức danh", "Chức danh"),
    (r"^Dân tộc", "Dân tộc"),
    (r"^Quốc tịch", "Quốc tịch"),
    (r"^Loại giấy (tờ|chứng thực)", "Loại giấy tờ"),
    (r"^(Số giấy (tờ|chứng thực)[^:]*|Số)$", "Số giấy tờ (CCCD/CMND)"),
    (r"^Ngày cấp$", "Ngày cấp"),
    (r"^Nơi cấp$", "Nơi cấp"),
    (r"^(Nơi đăng ký (hộ khẩu|địa chỉ) thường trú|Địa chỉ thường trú)", "Địa chỉ thường trú"),
    (r"^(Địa chỉ liên lạc|Chỗ ở hiện tại)", "Địa chỉ liên lạc"),
    (r"^Tên (công ty|doanh nghiệp) viết bằng tiếng Việt$|^Tên (công ty|doanh nghiệp)$", "Tên doanh nghiệp"),
    (r"^Tên (công ty|doanh nghiệp).*nước ngoài", "Tên tiếng nước ngoài"),
    (r"^Tên (công ty|doanh nghiệp).*viết tắt", "Tên viết tắt"),
]
REP_FIELDS = ["Họ và tên", "Giới tính", "Chức danh", "Ngày sinh", "Dân tộc", "Quốc tịch", "Loại giấy tờ",
              "Số giấy tờ (CCCD/CMND)", "Ngày cấp", "Nơi cấp", "Địa chỉ thường trú", "Địa chỉ liên lạc"]
NGANH_JUNK = {"Ngành, nghề", "chưa khớp mã", "ngành kinh tế", "Việt Nam", "chưa khớp", "mã với Hệ",
              "thống ngành", "kinh tế Việt", "Nam"}


def _canon(label):
    label = re.sub(r"\s+", " ", label.strip(" *:-"))
    for pat, name in LABEL_MAP:
        if re.search(pat, label):
            return name
    return label


def _clean(v):
    return re.sub(r"\s+", " ", v).strip()


def _pairs(text):
    """'Nhãn: giá trị   Nhãn 2: giá trị 2' -> [(nhãn, giá trị), ...]. Phần không có ':' -> (None, phần đó)."""
    segs = [s for s in re.split(r"\s{3,}", text.strip()) if s.strip()]
    out, i = [], 0
    while i < len(segs):
        seg = segs[i].strip()
        m = re.match(r"^([^:]{1,70}?):\s*(.*)$", seg)
        if m and not re.match(r"^\d", m.group(1)):
            label, val = m.group(1), m.group(2)
            if not val and i + 1 < len(segs) and not re.match(r"^[^:]{1,70}?:(\s|$)", segs[i + 1].strip()):
                val = segs[i + 1].strip()
                i += 1
            out.append((label, _clean(val)))
        else:
            out.append((None, _clean(seg)))
        i += 1
    return out


# ------------------------------------------------------------------ bộ phân tích chính

def in_share_skip(p):
    return "cổ phần" in p.group.lower() or "cổ đông" in p.group.lower()


class _Parser:
    def __init__(self):
        self.rows, self.reps = [], []
        self.group = "Thông tin chung"
        self.block = ""          # "[CŨ]" / "[MỚI]" trong phần Nội dung thay đổi
        self.sub = ""
        self.mode = "kv"         # kv | person | nganh | text
        self.top = ""            # mục đánh số hiện tại
        self.in_change = False
        self.last = None         # dòng (row) gần nhất, để nối phần xuống hàng
        self.person = None
        self.person_n = 0
        self.person_group = ""
        self.nganh = None
        self.nganh_seq = 0
        self.prev_wrapped = False
        self.table_head = []

    # -- ghi nhận
    def add(self, key, value, group=None):
        row = {"group": group or self.group, "key": key, "value": value}
        self.rows.append(row)
        self.last = row
        return row

    def _end_person(self):
        if self.person:
            n = self.person_n
            for k in REP_FIELDS + [k for k in self.person if k not in REP_FIELDS]:
                if self.person.get(k):
                    self.rows.append({"group": f"{self.person_group} #{n}", "key": k, "value": self.person[k]})
            if self.person_group == "Người đại diện theo pháp luật":
                self.reps.append(dict(self.person))
        self.person, self.last = None, None

    def _end_nganh(self):
        n = self.nganh
        if n and not n["skip"]:
            lines = n["lines"]
            if not n["code"] and any(l.lstrip().startswith("-") for l in lines):
                # mẫu cũ: cả danh sách ngành nghề liệt kê bằng gạch đầu dòng trong 1 ô -> tách từng ngành
                entries = []
                for l in lines:
                    if l.lstrip().startswith("-") or not entries:
                        entries.append(l.lstrip(" -").strip())
                    else:
                        entries[-1] += " " + l.strip()
                for e in entries:
                    self.nganh_seq += 1
                    self.rows.append({"group": self.group, "key": f"Ngành nghề #{self.nganh_seq}",
                                      "value": _clean(e.rstrip(";"))})
            else:
                val = (f"{n['code']} - " if n["code"] else "") + n["name"]
                if n["detail"]:
                    val += " | " + _clean(" ".join(n["detail"]))
                self.nganh_seq += 1
                self.rows.append({"group": self.group, "key": f"Ngành nghề #{self.nganh_seq}", "value": _clean(val)})
        self.nganh = None

    def set_section(self, group, mode):
        self._end_person()
        self._end_nganh()
        self.group, self.mode, self.last, self.table_head = group, mode, None, []
        self.nganh_seq = 0
        if mode in ("person", "items"):
            self.person_group, self.person_n = group, 0

    # -- xử lý từng dòng
    def feed(self, line):
        text, x0, x1 = line["text"], line["x0"], line["x1"]
        wrapped_before = self.prev_wrapped
        self.prev_wrapped = x1 >= RIGHT_MARGIN_X
        t = text.strip()
        if t == "*":
            return

        # --- mục đánh số cấp cao "1. Tên công ty", "2. Mã số doanh nghiệp: ..."
        m = TOP_RE.match(t)
        if m:
            body = m.group(2)
            for pat, name in TOP_KEYS:
                if re.search(pat, body):
                    self.on_top(name, body)
                    return

        if self.in_change:
            if t in ("Khối thông tin cũ", "Khối thông tin mới"):
                self.block = "[CŨ]" if t.endswith("cũ") else "[MỚI]"
                self.set_section(f"{self.block} Thông tin khác", "kv")  # các khoá đứng ngoài tiêu đề mục con
                self.sub = ""
                return
            if SUB_RE.match(t):
                name = t.rstrip(" :")
                if name.startswith("Người đại diện") and "khác" not in name:
                    mode = "person"
                elif name.startswith("Ngành"):
                    mode = "nganh"
                elif re.search(r"văn phòng đại diện|chi nhánh|địa điểm kinh doanh|người quản lý", name, re.I):
                    mode = "items"   # danh sách các mục lặp lại (mỗi mục bắt đầu khi khoá lặp lại)
                else:
                    mode = "kv"
                self.sub = name
                self.set_section(f"{self.block} {name}".strip(), mode)
                if name == "Địa chỉ trụ sở chính":
                    self.mode = "text"
                    self.add("Địa chỉ trụ sở chính", "")
                return

        if self.mode in ("person", "items"):
            self.feed_person(text, wrapped_before)
        elif self.mode == "nganh":
            self.feed_nganh(line, text)
        else:
            self.feed_kv(text, wrapped_before)

    def on_top(self, name, body):
        if name == "ten":
            self.set_section("Thông tin chung", "kv")
            self.top = name
            return
        if name == "reps":
            self.set_section("Người đại diện theo pháp luật", "person")
            self.top = name
            return
        if name == "change":
            self.set_section("Nội dung thay đổi", "kv")
            self.in_change = True
            self.top = name
            return
        # các mục còn lại là "key: value" ngay trên dòng tiêu đề (hoặc giá trị ở các dòng sau)
        self.set_section("Thông tin chung", "kv")
        self.in_change = False
        self.top = name
        key = {"mst": "Mã số doanh nghiệp", "ngay_tl": "Ngày thành lập", "dia_chi": "Địa chỉ trụ sở chính",
               "ngay_dk": "Ngày cấp đăng ký thay đổi", "noi_dk": "Nơi đăng ký", "ghi_chu": "Ghi chú"}[name]
        val = ""
        mm = re.match(r"^[^:]+:\s*(.*)$", body)
        if mm:
            val = _clean(mm.group(1))
        self.add(key, val)
        self.mode = "text"

    def feed_person(self, text, wrapped_before):
        prs = _pairs(text)
        if all(k is None for k, _ in prs):
            if self.last and wrapped_before:
                self.last["__v"] = _clean(self.last["__v"] + " " + text)
                self.person[self.last["__k"]] = self.last["__v"]
            return
        for k, v in prs:
            if k is None:
                if self.last and wrapped_before:
                    self.last["__v"] = _clean(self.last["__v"] + " " + v)
                    self.person[self.last["__k"]] = self.last["__v"]
                continue
            key = _canon(k)
            if self.person is None or key in self.person:
                self._end_person()
                self.person, self.person_n = {}, self.person_n + 1
            self.person[key] = v
            self.last = {"__k": key, "__v": v}

    def feed_kv(self, text, wrapped_before):
        prs = _pairs(text)
        has_label = any(k is not None for k, _ in prs)
        if has_label:
            for k, v in prs:
                if k is None:
                    self._continue(v, wrapped_before)
                    continue
                key = _canon(k)
                if v:
                    self.add(key, v)
                else:
                    self.last = None
            return
        # dòng không có ':' -> hàng bảng (nhãn + số) hoặc phần xuống hàng của giá trị trước
        cells = [p for _, p in prs]
        in_share = "cổ phần" in self.group.lower() or "cổ đông" in self.group.lower()
        if len(cells) >= 2 and all(NUM_RE.match(c) for c in cells[1:]):
            if in_share:        # bảng cổ phần/cổ đông: các số bị dính ô nên bỏ qua để khỏi sai dữ liệu
                self.last = None
                return
            head = self.table_head
            key = f"{head[0]}: {cells[0]}" if head else cells[0]
            if head and len(head) == len(cells):
                val = " | ".join(f"{h} {v}" for h, v in zip(head[1:], cells[1:]))
            else:
                val = " | ".join(cells[1:])
            self.add(key, val)
            self.last["__table"] = True
            return
        if len(cells) >= 2:
            self.table_head = cells  # dòng tiêu đề bảng
            self.last = None
            return
        self._continue(cells[0], wrapped_before)

    def _continue(self, v, wrapped_before):
        if not (self.last and (wrapped_before or self.mode == "text")):
            return
        if self.last.get("__table"):
            self.last["key"] = _clean(self.last["key"] + " " + v)
        elif in_share_skip(self):
            return
        else:
            self.last["value"] = _clean(self.last["value"] + " " + v)

    def feed_nganh(self, line, text):
        if line["x0"] > 400 or re.match(r"^(STT|Số)\s+Tên", text):
            return
        if text in NGANH_JUNK:
            return
        m = re.match(r"^(\d{1,3})\s+(.+?)\s{2,}(\d{4,5}(?:\(Chính\))?)\s*$", text)
        if m:
            self._end_nganh()
            # tên chạm sát lề phải của cột tên (x1 >= 435) => tên bị xuống dòng, dòng kế tiếp vẫn là tên
            name_open = len(line.get("seg_x1", [])) >= 2 and line["seg_x1"][-2] >= NAME_WRAP_X
            self.nganh = {"n": m.group(1), "name": _clean(m.group(2)), "code": m.group(3), "detail": [],
                          "skip": m.group(2).startswith("(Đối với"), "name_open": name_open, "lines": []}
            return
        m = re.match(r"^(\d{1,3})\s+(\S.*)$", text) if line["x0"] < 80 else None
        if m:
            self._end_nganh()
            body = re.split(r"\s{3,}", m.group(2))
            body = [b for b in body if b.strip() not in NGANH_JUNK]
            first = _clean(" ".join(body))
            self.nganh = {"n": m.group(1), "name": first, "code": "", "detail": [], "lines": [first],
                          "skip": m.group(2).startswith("(Đối với")}
            return
        if self.nganh:
            parts = " ".join(p for p in re.split(r"\s{3,}", text) if p.strip() not in NGANH_JUNK)
            if self.nganh.get("name_open"):
                self.nganh["name"] = _clean(self.nganh["name"] + " " + parts)
                self.nganh["name_open"] = False
            else:
                self.nganh["detail"].append(parts)
                self.nganh["lines"].append(parts)

    def finish(self):
        self._end_person()
        self._end_nganh()
        # bỏ các khoá phụ trợ nội bộ và dòng không có giá trị
        for r in self.rows:
            r.pop("__table", None)
        self.rows = [r for r in self.rows if r["value"] != ""]


def parse_lines(lines):
    p = _Parser()
    meta = []
    period = None
    header = []
    started = False
    for ln in lines:
        t = ln["text"]
        if FOOTER_RE.match(t):
            m = PERIOD_RE.search(t)
            if m:
                period = m.groups()
            continue
        if not started:
            if TOP_RE.match(t):
                started = True
            else:
                header.append(t)
                continue
        p.feed(ln)
    p.finish()
    rows = []
    if header:
        rows.append({"group": "Thông tin chung", "key": "Tên (đầu trang)", "value": _clean(header[0])})
        if len(header) > 1:
            rows.append({"group": "Thông tin chung", "key": "Tiêu đề bố cáo", "value": _clean(" ".join(header[1:]))})
    rows += p.rows
    if period:
        rows.append({"group": "Thông tin chung", "key": "Thời gian đăng từ ngày", "value": period[0]})
        rows.append({"group": "Thông tin chung", "key": "Thời gian đăng đến ngày", "value": period[1]})
    return rows, p.reps


def parse_pdf(path):
    """Trả về dict: ok, error, rows, reps. Không ném lỗi ra ngoài."""
    try:
        rows, reps = parse_lines(read_lines(path))
        has_mst = any(r["key"] == "Mã số doanh nghiệp" for r in rows)
        return {"ok": has_mst, "error": "" if has_mst else "không tìm thấy 'Mã số doanh nghiệp' (PDF khác mẫu?)",
                "rows": rows, "reps": reps}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "rows": [], "reps": []}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    res = parse_pdf(sys.argv[1])
    print("ok:", res["ok"], res["error"])
    last = None
    for r in res["rows"]:
        if r["group"] != last:
            print(f"\n== {r['group']}")
            last = r["group"]
        print(f"  {r['key']}: {r['value']}")
