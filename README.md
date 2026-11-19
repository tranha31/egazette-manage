# Egazette

Tra cứu bố cáo điện tử ([bocaodientu.dkkd.gov.vn](https://bocaodientu.dkkd.gov.vn)): nhập mã số thuế + loại công bố + khoảng ngày → hệ thống crawl, tách nội dung PDF,
lưu **MySQL** (dữ liệu) và **MinIO** (file PDF), cho tìm kiếm và xem so sánh thay đổi cũ → mới. **Đã có trong database thì không crawl lại.**

**Hướng dẫn sử dụng (có ảnh từng chức năng): [docs/HUONG_DAN_SU_DUNG.md](docs/HUONG_DAN_SU_DUNG.md)**

```
backend/             Flask API + worker crawl (Playwright, 2captcha) + tách PDF
frontend/            React + TypeScript (Vite)
minio/               Dockerfile build MinIO từ source
docker-compose.yml   frontend (nginx) + backend + MinIO (+ MySQL tuỳ chọn)
```

## Chạy bằng Docker (khuyến nghị)

```powershell
copy .env.example .env          # điền MINIO_ACCESS_KEY, MINIO_SECRET_KEY, DATABASE_URL, APIKEY_2CAPTCHA
docker compose up -d --build    # lần đầu vài phút: build MinIO từ source, tải Chromium
```
Mở http://127.0.0.1:8080. Dừng: `docker compose stop`. **Đừng** chạy `docker compose down -v` (xoá volume MinIO = mất toàn bộ PDF).

| Service | Cổng (chỉ 127.0.0.1) | Vai trò |
|---|---|---|
| `frontend` | 8080 | nginx phục vụ React và chuyển tiếp `/api` sang backend (cùng một địa chỉ) |
| `backend` | 8000 | API, worker crawl, tách PDF |
| `minio` | 9000, console 9001 | lưu PDF |
| `mysql` | 3307 | chỉ chạy khi bật `--profile mysql` |

- **Database:** `DATABASE_URL` trong `.env`. MySQL có sẵn trên máy chủ thì dùng host `host.docker.internal`. Muốn MySQL đi kèm: xoá dòng `DATABASE_URL`, chạy `docker compose --profile mysql up -d`.
- **Font:** bộ tách PDF cần **đúng** 4 file Times New Roman của Windows (`times`, `timesbd`, `timesi`, `timesbi` `.ttf`; font "tương thích" như Liberation có glyph khác nên giải mã sai).
  Compose mount chúng từ `C:/Windows/Fonts` (chỉ đọc); máy khác đặt `PDF_FONT_DIR`.
- **Trình duyệt crawl:** Chromium của Playwright chạy có giao diện trên màn hình ảo Xvfb (`HEADLESS=false`), vì reCAPTCHA hay chặn headless.
- **Mở cho máy khác:** `WEB_BIND=0.0.0.0` **và** `APP_USER` / `APP_PASSWORD` (dữ liệu có CCCD, địa chỉ cá nhân), nên đặt sau HTTPS.
- Sau khi sửa mã: `docker compose up -d --build backend frontend`.

## Chạy tay (phát triển)

Cần Python 3.14, Node 22, Chrome/Edge, Docker (cho MinIO) và một MySQL.

```powershell
docker compose up -d minio                       # key MinIO lấy từ .env gốc
cd backend
python -m venv venv ; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env                           # DATABASE_URL, APIKEY_2CAPTCHA (hoặc file api_key.txt)
python run.py                                    # http://127.0.0.1:8000, bảng tự tạo khi khởi động
cd ../frontend ; npm install ; npm run dev       # http://localhost:5173, Vite chuyển tiếp /api sang backend
```
Chạy một cổng: `npm run build` rồi `python run.py` (backend phục vụ luôn `frontend/dist`).

## Cấu hình chính

Key MinIO nằm ở `.env` **gốc** (compose và backend cùng đọc); các biến còn lại ở `backend/.env`. Mẫu: `.env.example`, `backend/.env.example`.

| Biến | Ý nghĩa (mặc định) |
|---|---|
| `DATABASE_URL` | `mysql+pymysql://USER:PASS@HOST:3306/DB?charset=utf8mb4` |
| `MINIO_ENDPOINT` · `MINIO_ACCESS_KEY` · `MINIO_SECRET_KEY` · `MINIO_BUCKET` | MinIO (`127.0.0.1:9000`, bucket `egazette` tự tạo); `MINIO_SECURE=true` nếu HTTPS |
| `APIKEY_2CAPTCHA` / `API_KEY_FILE` | key 2captcha; trống thì crawl tạm dừng, xem/tìm kiếm vẫn dùng được |
| `APP_USER` · `APP_PASSWORD` | bật đăng nhập HTTP Basic (nên bật khi mở ra ngoài) |
| `HEADLESS` · `MIN_BALANCE` | chế độ trình duyệt (`false`) · số dư tối thiểu để chạy (`0.01` USD) |
| `TODAY_RECHECK_MINUTES` | vừa crawl trong N phút thì coi "hôm nay" đã đủ (`60`) |
| `PDF_FONT_DIR` | thư mục chứa 4 font Times New Roman (mặc định `C:\Windows\Fonts`) |
| `START_WORKER` · `PER_PAGE` | bật worker (`true`; nhiều tiến trình thì chỉ để một cái bật) · cỡ trang (`25`) |
| `CORS_ORIGINS` · `TRUST_PROXY` | khi frontend khác địa chỉ · khi đứng sau reverse proxy |

## Tính năng

- **Crawl:** nhập thủ công (nhiều MST, loại công bố, khoảng ngày; *Kiểm tra trước* không tạo job; *Bắt buộc crawl lại*) hoặc **hàng loạt từ file Excel**.
- **Công việc:** hàng đợi crawl, nhật ký, huỷ / chạy lại. Hết số dư 2captcha hoặc MinIO lỗi thì cả hàng đợi tự tạm dừng, có nút *Tiếp tục*.
- **Tìm bố cáo:** theo tên, MST, địa chỉ, người đại diện, CCCD, loại, ngày đăng; tìm trong toàn bộ nội dung PDF; xuất Excel. Tìm không phân biệt hoa thường và dấu tiếng Việt (MySQL `utf8mb4_unicode_ci`).
- **Chi tiết bố cáo:** bảng so sánh **cũ → mới** (đánh dấu từng từ khác nhau, ngành nghề ghép theo mã ngành), thông tin chung, người đại diện, toàn bộ nội dung, bản PDF.
- **Doanh nghiệp:** mỗi MST một dòng, có thao tác xem danh sách bố cáo; trang chi tiết kèm các khoảng thời gian đã crawl.
- Danh sách lớn phân trang phía server (10/25/50/100, nằm trên URL); giao diện sáng/tối, dùng được trên điện thoại.

### Crawl hàng loạt từ Excel

Tải file mẫu ở tab *Crawl hàng loạt* (cùng định dạng tool Excel cũ). Mỗi dòng:

| Cột | Nhận |
|---|---|
| Mã số thuế | 10 hoặc 13 số, một mã mỗi dòng (ô số bị mất số 0 đầu thì tự bù) |
| Loại công bố | mã (`AMEND`), tên loại, `ALL`, hoặc nhiều loại cách nhau `,` hay `;` |
| Từ ngày / Đến ngày | `dd/MM/yyyy`, `yyyy-MM-dd` hoặc ô ngày Excel; bỏ trống một hoặc cả hai đầu được |
| Crawl lại | `Có` / `Không` |

Tải lên **chỉ để xem trước**: mỗi dòng hợp lệ / lỗi (kèm lý do và số dòng) / trùng, cần crawl hay đã có trong database. Bấm *Crawl N cặp* mới tạo job; dòng lỗi bị bỏ qua, dòng trùng gửi một lần.
Giới hạn: `.xlsx` ≤ 5 MB, 500 dòng, 1000 cặp (MST × loại) mỗi lần, vì mỗi cặp tốn một lượt captcha.

## Quy tắc "đã có thì không crawl"

Khoá một lần crawl là **(MST, loại công bố, khoảng ngày đăng)**. Logic ở `backend/app/coverage.py`.

1. Bỏ trống ngày = từ 01/01/2000 đến hôm nay; "Đến ngày" ở tương lai bị cắt về hôm nay.
2. **Khoảng đã có** = các lần crawl thành công trước đó + các job đang chờ/chạy (tránh hai người gửi cùng yêu cầu).
3. **Hôm nay chưa kết thúc** nên một lần crawl chỉ được coi là phủ tới *ngày crawl − 1*; riêng "hôm nay" chỉ tính nếu vừa crawl trong `TODAY_RECHECK_MINUTES`.
4. **Khoảng cần crawl** = khoảng yêu cầu − khoảng đã có. Đã có trọn → ghi job "Bỏ qua", không crawl. Có một phần → chỉ crawl phần thiếu.
   Thiếu nhiều đoạn rời → crawl một lần cho đoạn bao ngoài (bố cáo trùng không nhân đôi nhờ khoá duy nhất `(MST, loại, ngày giờ đăng)`).
5. **Chỉ ghi nhận "đã crawl" khi crawl trọn vẹn** và trang trả bảng kết quả hợp lệ; lỗi, huỷ hoặc captcha sai thì lần sau vẫn crawl lại.

## PDF trên MinIO

Backend không giữ PDF trên đĩa: tải về thư mục tạm → tách nội dung → upload MinIO → ghi database → xoá file tạm. Bảng `announcements` lưu `pdf_bucket`, `pdf_path` (object key,
vd `pdf/0999999991/AMEND/..._20260512_170600.pdf`) và `pdf_size`. Xem PDF qua `/api/files/{id}`: backend stream từ MinIO nên đăng nhập vẫn có tác dụng.

- **MinIO lỗi:** xem/tìm kiếm vẫn chạy, crawl tạm dừng có thông báo, `/api/files` trả 502; tự phục hồi khi MinIO chạy lại.
- **Chuyển PDF cũ trên đĩa lên MinIO:** `python -m app.migrate_pdfs` trong `backend` (`--dry-run` để xem trước, `--delete-local` để xoá file cục bộ sau khi đã kiểm tra). Nguồn: `LEGACY_STORAGE_DIR` (mặc định `backend/storage`).
  Database cũ tự được thêm cột `pdf_bucket`, `pdf_size` khi backend khởi động.
- **Chuyển dữ liệu từ tool Excel cũ:** `python -m app.import_excel <ketqua.xlsx>` (upload luôn PDF lên MinIO).
- **Image MinIO:** MinIO đã ngừng phát hành image/binary chính thức và repo đã archived, nên `minio/Dockerfile` build từ source ở tag cố định (AGPL-3.0).
  Bản này không còn nhận bản vá bảo mật: chỉ dùng trong mạng nội bộ. Key mặc định là key quản trị; môi trường thật nên tạo access key riêng cho bucket qua console (9001).
  Container từ chối chạy nếu thiếu key hoặc dùng `minioadmin`. Đổi key: sửa `.env`, `docker compose up -d --force-recreate minio`, khởi động lại backend.

## API

Mọi đường dẫn dưới `/api`, trả JSON (lỗi: `{"error": "..."}`). Danh sách phân trang trả `{items, total, page, per_page, pages}` với `?page=`, `?per_page=` (1–200).
Thao tác ghi (POST) cần header `X-Requested-With: XMLHttpRequest` (chống CSRF khi dùng Basic auth); frontend tự gửi.

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/meta` · `/overview` · `/worker` | loại công bố và nhãn trạng thái · số liệu tổng quan · trạng thái hàng đợi (`POST /worker/resume` để tiếp tục) |
| POST | `/crawl` · `/crawl/preview` | tạo job (`{tax_codes, types, date_from, date_to, force}`) · kiểm tra trước, không tạo job |
| GET · POST | `/crawl/template.xlsx` · `/crawl/import` · `/crawl/batch` | file mẫu · đọc file Excel và xem trước (không tạo job) · tạo job từ các dòng đã xem trước |
| GET · POST | `/jobs` · `/jobs/{id}` · `/jobs/{id}/cancel` · `/jobs/{id}/retry` | danh sách · chi tiết kèm nhật ký · huỷ · chạy lại |
| GET | `/search` · `/search/export.xlsx` | tìm bố cáo (`q, deep, tax_code, ann_type, date_from, date_to, pdf_only`) · xuất Excel cùng bộ lọc |
| GET | `/announcements/{id}` · `/files/{id}[?download=1]` | chi tiết bố cáo · file PDF |
| GET | `/companies` · `/companies/{mst}` · `/people` | doanh nghiệp · chi tiết kèm khoảng đã crawl · người đại diện (`name, id_number, tax_code`) |

## Kiểm thử

```powershell
cd backend ; pytest            # SQLite tạm, MinIO giả trong bộ nhớ, crawler giả: không gọi trang bố cáo, không tốn tiền 2captcha
cd frontend ; npm test ; npm run build
```
Tuỳ chọn: `TEST_DATABASE_URL` (chạy trên MySQL, **phải là database test riêng** vì test xoá và tạo lại bảng); `TEST_MINIO_ENDPOINT`, `TEST_MINIO_ACCESS_KEY`, `TEST_MINIO_SECRET_KEY` (thêm test với MinIO thật, dùng bucket tạm).
Các test đối chiếu nội dung PDF thật cần thư mục `SAMPLE_PDF_DIR` chứa PDF mẫu **và** file `expected.json` (tên công ty, người đại diện, số CCCD... mong đợi, đặt cạnh PDF, **ngoài repo** để dữ liệu thật không đi vào mã nguồn); thiếu một trong hai thì các test đó tự bỏ qua. Cấu trúc file: xem `backend/tests/conftest.py`.

## Cần biết

- **Crawl thật chưa được kiểm chứng qua giao diện web** (kể cả trong Docker): logic điền form, giải captcha, đọc bảng, tải PDF lấy từ tool Excel cũ đã chạy được. Nên thử một MST nhỏ trước.
- Chưa biết trang có tính bố cáo của **đúng ngày "Đến ngày"** hay không (thử từ = đến = một ngày đã biết có bố cáo). Nếu không, cần cộng thêm 1 ngày trong `backend/app/crawler.py`.
- Kết quả 0 dòng mà trang không có hàng tiêu đề được coi là *chưa xác nhận* (job "Xong (có lưu ý)", không ghi nhận đã crawl).
- Mỗi lần crawl tốn một lượt 2captcha. Chỉ có một worker nên job chạy lần lượt.
- Chưa phân quyền theo người dùng, chỉ có một mật khẩu chung. Bảng cổ phần / cổ đông trong PDF chưa được tách.
