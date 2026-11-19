"""
Quyết định có cần crawl hay không, dựa trên các khoảng thời gian ĐÃ crawl thành công.

Khoá của một lần crawl là bộ ba (mã số thuế, loại công bố, khoảng ngày đăng). Quy tắc:

1. Khoảng yêu cầu R = [từ ngày, đến ngày] (đóng hai đầu).
   - Không nhập ngày  -> R = [FLOOR, hôm nay]  ("tất cả bố cáo từ trước đến nay").
   - Nhập thiếu một đầu -> đầu thiếu là FLOOR / hôm nay.
   - "Đến ngày" ở tương lai bị cắt về hôm nay (không thể có bố cáo của ngày chưa tới).
2. Một lần crawl đã xong KHÔNG chắc phủ hết ngày crawl: ngày hôm đó chưa kết thúc nên còn có thể có
   bố cáo mới đăng sau đó. Vì vậy khoảng đã phủ hiệu lực chỉ tới (ngày crawl - 1), trừ khi lần crawl đó
   mới cách đây chưa tới TODAY_RECHECK_MINUTES phút và vẫn trong cùng ngày.
3. Khoảng cần crawl = R trừ đi (khoảng đã phủ trong database + khoảng của các job đang chờ/đang chạy).
   - Rỗng      -> bỏ qua, không crawl ("đã có").
   - Một phần  -> chỉ crawl phần thiếu. Nếu thiếu nhiều đoạn rời nhau thì crawl 1 lần cho đoạn bao
                  ngoài (từ đầu đoạn thiếu đầu tiên đến cuối đoạn thiếu cuối cùng) để chỉ tốn 1 lượt captcha.
                  Bố cáo trùng được gộp theo (MST, loại, ngày giờ đăng) nên không bị nhân đôi.
4. Chỉ ghi nhận "đã phủ" khi crawl thành công trọn vẹn (xem worker.py). Crawl lỗi thì không ghi.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

FLOOR = date(2000, 1, 1)  # mốc "từ trước đến nay"
ONE = timedelta(days=1)


@dataclass(frozen=True, order=True)
class Interval:
    start: date
    end: date

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError(f"khoảng không hợp lệ: {self.start} > {self.end}")

    def __str__(self):
        if self.start == self.end:
            return f"{self.start:%d/%m/%Y}"
        return f"{self.start:%d/%m/%Y} → {self.end:%d/%m/%Y}"


def merge(intervals):
    """Gộp các khoảng chồng nhau hoặc liền kề (kết thúc hôm trước, bắt đầu hôm sau)."""
    out = []
    for iv in sorted(intervals):
        if out and iv.start <= out[-1].end + ONE:
            if iv.end > out[-1].end:
                out[-1] = Interval(out[-1].start, iv.end)
        else:
            out.append(iv)
    return out


def subtract(req, covered):
    """Phần của `req` chưa nằm trong `covered`. Trả về list[Interval] theo thứ tự thời gian."""
    gaps, cursor = [], req.start
    for c in merge(covered):
        if c.end < cursor:
            continue
        if c.start > req.end:
            break
        if c.start > cursor:
            gaps.append(Interval(cursor, min(c.start - ONE, req.end)))
        cursor = max(cursor, c.end + ONE)
        if cursor > req.end:
            return gaps
    if cursor <= req.end:
        gaps.append(Interval(cursor, req.end))
    return gaps


def request_interval(date_from, date_to, today):
    """Chuẩn hoá khoảng người dùng nhập. Trả về None nếu khoảng nằm hoàn toàn trong tương lai."""
    start = date_from or FLOOR
    end = min(date_to or today, today)
    if start > end:
        return None
    return Interval(start, end)


def effective_interval(date_from, date_to, crawled_at, now, recheck_minutes):
    """Khoảng thực sự đã phủ của một lần crawl (xem quy tắc 2). None nếu chưa phủ được ngày nào."""
    crawled_day = crawled_at.date()
    cutoff = crawled_day - ONE
    if crawled_day == now.date() and (now - crawled_at) < timedelta(minutes=recheck_minutes):
        cutoff = crawled_day  # vừa crawl xong, chấp nhận "hôm nay" là đã đủ
    end = min(date_to, cutoff)
    return Interval(date_from, end) if end >= date_from else None


@dataclass
class Plan:
    status: str                      # covered | partial | missing | future | forced
    requested: Interval | None       # khoảng yêu cầu sau chuẩn hoá
    covered: list = field(default_factory=list)  # phần của khoảng yêu cầu đã có (trong DB hoặc đang xử lý)
    gaps: list = field(default_factory=list)     # các đoạn còn thiếu
    crawl: Interval | None = None    # khoảng sẽ ghi nhận "đã phủ" sau khi crawl xong (đoạn bao ngoài các gap)
    site_from: date | None = None    # giá trị điền vào ô "Từ ngày"/"Đến ngày" trên trang
    site_to: date | None = None      # cả hai None = không lọc ngày (lấy tất cả)

    @property
    def needs_crawl(self):
        return self.crawl is not None


def make_plan(date_from, date_to, covered_records, pending, now, recheck_minutes=60, force=False):
    """
    covered_records: iterable (date_from, date_to, crawled_at) các lần crawl thành công trong DB.
    pending: iterable Interval của các job đang chờ/đang chạy (coi như sắp được phủ).
    """
    today = now.date()
    req = request_interval(date_from, date_to, today)
    if req is None:
        return Plan("future", None)

    have = []
    for f, t, at in covered_records:
        iv = effective_interval(f, t, at, now, recheck_minutes)
        if iv:
            have.append(iv)
    have += list(pending)

    if force:
        gaps, status = [req], "forced"
    else:
        gaps = subtract(req, have)
        covered = subtract_inverse(req, gaps)
        if not gaps:
            return Plan("covered", req, covered=covered)
        status = "partial" if covered else "missing"
    crawl = Interval(gaps[0].start, gaps[-1].end)

    no_dates = date_from is None and date_to is None
    if no_dates and crawl == Interval(FLOOR, today):
        site_from = site_to = None            # lấy tất cả: để trống 2 ô ngày
    else:
        site_from, site_to = crawl.start, crawl.end
    covered = [] if force else subtract_inverse(req, gaps)
    return Plan(status, req, covered=covered, gaps=gaps, crawl=crawl, site_from=site_from, site_to=site_to)


def subtract_inverse(req, gaps):
    """Phần của req không nằm trong gaps (= phần đã có)."""
    if not gaps:
        return [req]
    out, cursor = [], req.start
    for g in gaps:
        if g.start > cursor:
            out.append(Interval(cursor, g.start - ONE))
        cursor = g.end + ONE
    if cursor <= req.end:
        out.append(Interval(cursor, req.end))
    return out


def describe(plan):
    """Câu mô tả bằng tiếng Việt cho người dùng."""
    if plan.status == "future":
        return "Khoảng thời gian nằm hoàn toàn trong tương lai, chưa có bố cáo."
    if plan.status == "covered":
        return f"Đã có trong database (đã crawl phủ {plan.requested}), không crawl lại."
    if plan.status == "forced":
        return f"Crawl lại theo yêu cầu: {plan.requested}."
    have = "; ".join(str(i) for i in plan.covered)
    need = "; ".join(str(i) for i in plan.gaps)
    if plan.status == "partial":
        txt = f"Đã có một phần ({have}). Cần crawl bổ sung: {need}"
        if len(plan.gaps) > 1:
            txt += f" → crawl 1 lần cho {plan.crawl}"
        return txt + "."
    return f"Chưa có trong database. Cần crawl: {plan.crawl}."
