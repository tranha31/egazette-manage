"""
Crawler bocaodientu.dkkd.gov.vn bằng Playwright + giải reCAPTCHA bằng 2captcha.

Giao diện chung (worker chỉ phụ thuộc vào đây, nên test được bằng crawler giả):

    crawler.open(); crawler.close(); crawler.check_balance()
    result = crawler.crawl(tax, typ, site_from, site_to, handle_row, should_stop)
        handle_row(info, fetch_pdf)   được gọi cho từng dòng kết quả
            info      = {"time", "start", "end", "name_code", "place", "type"}
            fetch_pdf = hàm (dest: Path) -> (ok: bool, mô_tả: str)  tải PDF của dòng đó về `dest`
        trả về CrawlResult(rows=<số dòng>, verified=<trang có trả kết quả hợp lệ không>)
"""
import re
import time
from dataclasses import dataclass
from pathlib import Path

URL = "https://bocaodientu.dkkd.gov.vn/egazette/Forms/Egazette/ANNOUNCEMENTSListingInsUpd.aspx"

ID_TYPE = "#ctl00_C_ANNOUNCEMENT_TYPE_IDFilterFld"
ID_TAX = "#ctl00_C_ENT_GDT_CODEFld"
ID_FROM = "#ctl00_C_PUBLISH_DATEFilterFldFrom"
ID_TO = "#ctl00_C_PUBLISH_DATEFilterFldTo"
ID_BTN = "#ctl00_C_BtnFilter"
ID_GRID = "#ctl00_C_CtlList"
ID_CAPTCHA_BOX = ".g-recaptcha"
ID_CAPTCHA_TOKEN = "#g-recaptcha-response"

CAPTCHA_RETRIES = 3
PDF_WAIT_MS = 20000

# Lỗi 2captcha mà thử lại cũng vô ích -> dừng cả hàng đợi
FATAL_2CAPTCHA = {
    "ERROR_ZERO_BALANCE": "Hết số dư 2captcha",
    "ERROR_WRONG_USER_KEY": "API key 2captcha sai",
    "ERROR_KEY_DOES_NOT_EXIST": "API key 2captcha không tồn tại",
    "ERROR_IP_NOT_ALLOWED": "IP máy này không được phép dùng API key",
    "IP_BANNED": "IP bị 2captcha chặn",
    "ERROR_ACCOUNT_SUSPENDED": "Tài khoản 2captcha bị khoá",
}


class StopRun(Exception):
    """Không thể tiếp tục (hết tiền, sai key...). Worker sẽ tạm dừng cả hàng đợi chứ không đánh dấu job hỏng."""


class Cancelled(Exception):
    pass


@dataclass
class CrawlResult:
    rows: int
    verified: bool  # True: trang đã trả bảng kết quả hợp lệ (có dòng dữ liệu hoặc có hàng tiêu đề)


class PlaywrightCrawler:
    def __init__(self, api_key, headless=False, min_balance=0.01, log=print):
        self.api_key, self.headless, self.min_balance, self.log = api_key, headless, min_balance, log
        self._pw = self._browser = self.page = self.solver = None

    # ---- vòng đời
    def open(self):
        from playwright.sync_api import sync_playwright
        from twocaptcha import TwoCaptcha
        if not self.api_key:
            raise StopRun("Chưa cấu hình API key 2captcha (APIKEY_2CAPTCHA hoặc file api_key.txt)")
        self.solver = TwoCaptcha(self.api_key)
        self._pw = sync_playwright().start()
        last = None
        # Ưu tiên Chrome / Edge có sẵn trên máy; không có (vd trong Docker) thì dùng Chromium của Playwright (channel=None)
        for channel in ("chrome", "msedge", None):
            try:
                self._browser = self._pw.chromium.launch(headless=self.headless, channel=channel)
                break
            except Exception as e:  # noqa: BLE001
                last = e
        if not self._browser:
            self._pw.stop()
            raise RuntimeError(f"Không mở được Chrome / Edge / Chromium của Playwright: {last}")
        self.page = self._browser.new_context(accept_downloads=True, locale="vi-VN").new_page()

    def close(self):
        for obj, fn in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, fn)()
            except Exception:  # noqa: BLE001
                pass
        self._pw = self._browser = self.page = None

    # ---- 2captcha
    def check_balance(self):
        try:
            bal = float(self.solver.balance())
        except Exception as e:  # noqa: BLE001
            self._raise_if_fatal(e)
            self.log(f"(không đọc được số dư 2captcha: {e!r})")
            return None
        self.log(f"Số dư 2captcha: {bal:.4f} USD")
        if bal < self.min_balance:
            raise StopRun(f"Số dư 2captcha chỉ còn {bal:.4f} USD (ngưỡng tối thiểu {self.min_balance} USD)")
        return bal

    @staticmethod
    def _raise_if_fatal(e):
        for code, msg in FATAL_2CAPTCHA.items():
            if code in str(e):
                raise StopRun(f"{msg} ({code})") from e

    def _solve(self, sitekey):
        last = None
        for attempt in range(1, CAPTCHA_RETRIES + 1):
            try:
                self.log(f"Gửi captcha cho 2captcha (lần {attempt}/{CAPTCHA_RETRIES}), chờ 10-60s...")
                return self.solver.recaptcha(sitekey=sitekey, url=URL)["code"]
            except Exception as e:  # noqa: BLE001
                self._raise_if_fatal(e)
                last = e
                self.log(f"2captcha lỗi: {e!r}")
        raise RuntimeError(f"giải captcha thất bại sau {CAPTCHA_RETRIES} lần: {last!r}")

    # ---- tìm kiếm
    def _fill_and_search(self, tax, typ, site_from, site_to):
        from playwright.sync_api import TimeoutError as PWTimeout
        page = self.page
        page.goto(URL, wait_until="domcontentloaded")
        try:  # đổi loại công bố làm trang tự postback
            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                page.select_option(ID_TYPE, typ)
        except PWTimeout:
            pass
        page.fill(ID_TAX, tax)
        if site_from and site_to:  # trang yêu cầu điền cả hai ô ngày hoặc để trống cả hai
            page.fill(ID_FROM, f"{site_from:%d/%m/%Y}")
            page.fill(ID_TO, f"{site_to:%d/%m/%Y}")
        page.wait_for_selector(ID_CAPTCHA_TOKEN, state="attached", timeout=30000)
        sitekey = page.get_attribute(ID_CAPTCHA_BOX, "data-sitekey")
        token = self._solve(sitekey)
        page.evaluate("t => { document.querySelector('#g-recaptcha-response').value = t; }", token)
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            page.click(ID_BTN)

    def _data_rows(self):
        rows = self.page.locator(f"{ID_GRID} > tbody > tr, {ID_GRID} > tr")
        return rows, [i for i in range(rows.count()) if rows.nth(i).locator("> td").count() >= 7]

    @staticmethod
    def _parse_row(row):
        cells = row.locator("> td")
        txt = [re.sub(r"\s+", " ", cells.nth(i).inner_text()).strip() for i in range(cells.count())]
        return {"time": txt[0], "start": txt[1], "end": txt[2], "name_code": txt[3], "place": txt[4], "type": txt[5]}

    def _save_pdf_for_row(self, row, dest: Path):
        """Bấm biểu tượng PDF ở ô cuối, bắt PDF qua download hoặc response."""
        from playwright.sync_api import TimeoutError as PWTimeout
        captured = {}

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "").lower()
                if "pdf" in ct or "octet-stream" in ct:
                    captured["body"] = resp.body()
            except Exception:  # noqa: BLE001
                pass

        page, ctx = self.page, self.page.context
        ctx.on("response", on_response)
        try:
            target = row.locator("> td").last.locator("a, input[type=image], img").first
            if target.count() == 0:
                return False, "không thấy nút PDF"
            t0 = time.time()
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with page.expect_download(timeout=PDF_WAIT_MS) as dl:
                    target.click()
                dl.value.save_as(dest)
                return True, "download"
            except PWTimeout:
                pass
            while time.time() - t0 < PDF_WAIT_MS / 1000 and "body" not in captured:
                page.wait_for_timeout(300)
            for pg in list(ctx.pages):
                if pg != page:
                    try:
                        pg.close()
                    except Exception:  # noqa: BLE001
                        pass
            if "body" in captured:
                dest.write_bytes(captured["body"])
                return True, "response"
            return False, "không bắt được PDF"
        finally:
            ctx.remove_listener("response", on_response)

    def crawl(self, tax, typ, site_from, site_to, handle_row, should_stop=lambda: False):
        from playwright.sync_api import TimeoutError as PWTimeout
        page = self.page
        self._fill_and_search(tax, typ, site_from, site_to)
        page_no, total = 1, 0
        verified = self.page.locator(f"{ID_GRID} th").count() > 0   # có hàng tiêu đề => trang đã trả kết quả
        while True:
            _, idxs = self._data_rows()
            if idxs:
                verified = True
            self.log(f"Trang {page_no}: {len(idxs)} dòng")
            for i in idxs:
                if should_stop():
                    raise Cancelled()
                rows, _ = self._data_rows()  # truy vấn lại vì postback làm handle cũ hết hạn
                row = rows.nth(i)
                info = self._parse_row(row)
                handle_row(info, lambda dest, _row=row: self._save_pdf_for_row(_row, dest))
                total += 1
            nxt = page.locator(f"{ID_GRID} a[href*='Page${page_no + 1}']")
            if nxt.count() == 0:
                break
            with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                nxt.first.click()
            page_no += 1
        return CrawlResult(rows=total, verified=verified)


def make_crawler(config, log):
    """Tạo crawler theo cấu hình. (Test dùng crawler giả nên không đi qua đây.)"""
    return PlaywrightCrawler(config.api_key(), headless=config.HEADLESS, min_balance=config.MIN_BALANCE, log=log)
