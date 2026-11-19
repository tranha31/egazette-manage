# Egazette

Tra cứu bố cáo điện tử (bocaodientu.dkkd.gov.vn): nhập mã số thuế + loại công bố + khoảng thời gian, hệ thống crawl,
tách nội dung PDF, lưu dữ liệu vào **MySQL**, lưu file PDF vào **MinIO** và cho tìm kiếm / xem lại. **Đã có trong database thì không crawl lại.**

Dự án tách hai phần độc lập, giao tiếp qua REST API JSON:

```
egazette_web/
├── backend/            Python (Flask + SQLAlchemy + Playwright): API, crawler, hàng đợi, tách PDF, MySQL, MinIO
├── frontend/           React + TypeScript (Vite): toàn bộ giao diện
├── minio/              Dockerfile build MinIO từ source (MinIO không còn phát hành image chính thức)
└── docker-compose.yml  frontend (nginx) + backend + MinIO (+ MySQL 8 tuỳ chọn)
```

## Chạy nhanh

Cần: Python (đã kiểm tra với 3.14), Node (đã kiểm tra với 22), Docker (cho MySQL), một MinIO đang chạy (xem bên dưới), Windows có Chrome/Edge (crawler dùng trình duyệt có sẵn và font
Times New Roman của Windows để giải mã PDF).

```powershell
# 1. MySQL (bỏ qua nếu dùng MySQL có sẵn: chỉ cần sửa DATABASE_URL trong backend/.env)
docker compose --profile mysql up -d mysql    # đợi ~30 giây

# 2. MinIO (lưu PDF): tạo .env cạnh docker-compose.yml chứa MINIO_ACCESS_KEY / MINIO_SECRET_KEY, rồi
copy .env.example .env                    # điền hai key (hoặc dùng MinIO có sẵn: xem mục "Lưu PDF trên MinIO")
docker compose up -d minio                # lần đầu build từ source mất vài phút

# 3. Backend  (http://127.0.0.1:8000, API ở /api)
cd backend
python -m venv venv ; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env                    # điền APIKEY_2CAPTCHA (hoặc tạo file api_key.txt chứa key)
python run.py

# 4. Frontend  (http://localhost:5173; Vite tự chuyển tiếp /api sang backend)
cd ../frontend
npm install
npm run dev
```

Chạy thật chỉ cần một địa chỉ: `npm run build` trong `frontend/`, rồi `python run.py`. Backend tự phục vụ thư mục
`frontend/dist` ở `/` (kèm fallback cho React Router), API vẫn ở `/api`.

Dùng MySQL có sẵn: sửa `DATABASE_URL` trong `backend/.env`
(`mysql+pymysql://USER:PASSWORD@HOST:3306/DBNAME?charset=utf8mb4`). Bảng tự tạo khi khởi động (`backend/schema.sql` để tham khảo).

Chuyển dữ liệu từ tool Excel cũ sang web:
```powershell
cd backend
python -m app.import_excel ..\..\egazette\output\ketqua_20261111_092509.xlsx
```

## Màn hình (frontend)

| Trang | Việc làm được |
|---|---|
| **Crawl** | Hai tab. **Nhập thủ công:** nhiều MST, loại công bố (hoặc tất cả), khoảng ngày; *Kiểm tra trước* cho biết từng cặp đã có trong DB chưa mà không tạo job; tuỳ chọn *Bắt buộc crawl lại*. **Hàng loạt từ file Excel:** tải file mẫu, điền, tải lên → xem trước từng dòng (hợp lệ / lỗi / trùng, cần crawl hay đã có) → xác nhận mới tạo job. Xem mục "Crawl hàng loạt" bên dưới. |
| **Công việc** | Hàng đợi crawl: trạng thái, nhật ký, huỷ / chạy lại. Tự làm mới khi còn việc chưa xong. Hết số dư 2captcha thì hàng đợi tự tạm dừng, có nút *Tiếp tục* ở đầu trang. |
| **Tìm bố cáo** | Từ khoá (tên DN, MST, địa chỉ, tên người đại diện, CCCD), lọc MST / loại / ngày đăng, tuỳ chọn tìm trong toàn bộ nội dung PDF, xuất Excel. Bộ lọc nằm trên URL nên chia sẻ / tải lại được. |
| **Chi tiết** | Các tab: **Thay đổi cũ → mới** (bảng so sánh), Thông tin chung, Người đại diện (thẻ), Toàn bộ nội dung (nhóm - khoá - giá trị), Bản PDF. |
| **Doanh nghiệp** | Mỗi MST một dòng. Cột *Thao tác*: **Xem bố cáo** (mở danh sách bố cáo của MST đó, có phân trang và xuất Excel) và **Chi tiết** (lịch sử bố cáo, người đại diện, **các khoảng thời gian đã crawl**). |

**Bảng so sánh cũ / mới** (`frontend/src/compare.ts`, có test): ghép các nhóm `[CŨ] X` và `[MỚI] X` của PDF thành bảng 3 cột
*Chỉ tiêu | Nội dung cũ | Nội dung mới*. Mỗi dòng là *đã đổi* (tô riêng từng từ khác nhau), *thêm mới* hoặc *đã bỏ*; mặc định chỉ
hiện dòng thay đổi, có công tắc để hiện cả dòng không đổi. Danh sách ngành nghề được ghép theo **mã ngành** (không theo số thứ tự)
nên thêm/bớt một ngành không làm lệch cả danh sách. Tên mục lệch giữa hai mẫu PDF ("Thông tin cổ phần" / "Thông tin về cổ phần") được coi là một.

**Phân trang:** danh sách lớn (tìm bố cáo, doanh nghiệp, người đại diện, công việc) phân trang phía server, có số trang, nhảy
đầu/cuối và chọn cỡ trang 10/25/50/100; trang và cỡ trang nằm trên URL. Các bảng nhỏ hơn (bố cáo của một doanh nghiệp,
khoảng đã crawl, kết quả kiểm tra, từng mục trong bảng so sánh, người đại diện) phân trang phía client.
Giao diện có chế độ sáng/tối (theo hệ điều hành, đổi được ở chân thanh bên) và dùng được trên điện thoại.

Tìm kiếm trên MySQL không phân biệt hoa thường và dấu tiếng Việt (`utf8mb4_unicode_ci`): `lu thanh long` khớp `LỮ THÀNH LONG`.

## REST API (backend)

Mọi đường dẫn dưới `/api`, trả JSON (lỗi: `{"error": "..."}`). Ngày: `YYYY-MM-DD`; ngày giờ: `YYYY-MM-DDTHH:MM:SS`.
Danh sách có phân trang: `{items, total, page, per_page, pages}` với `?page=` và `?per_page=` (1–200, mặc định 25).

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/meta` | Loại công bố, nhãn trạng thái job, `per_page`, đang bật mật khẩu hay không |
| GET | `/api/overview` | Số liệu tổng quan, 8 job và 8 bố cáo mới nhất |
| POST | `/api/crawl` | `{tax_codes, types, date_from, date_to, force}` → kiểm tra + tạo job; trả `{results, queued, skipped}` (lỗi nhập: 400 `{error, errors[]}`) |
| POST | `/api/crawl/preview` | Như trên nhưng không tạo job; trả `{items, invalid, truncated}` |
| GET | `/api/crawl/template.xlsx` | Tải file Excel mẫu để crawl hàng loạt |
| POST | `/api/crawl/import` | Tải file Excel lên (multipart, trường `file`) → xem trước từng dòng, **không tạo job**: `{filename, rows[], totals}` |
| POST | `/api/crawl/batch` | `{rows: [{tax_code, types[], date_from, date_to, force}]}` → tạo job cho các dòng đã xem trước (server kiểm tra lại); trả như `/api/crawl` |
| GET | `/api/jobs?status=&page=` · `/api/jobs/{id}` | Danh sách job · chi tiết kèm nhật ký |
| POST | `/api/jobs/{id}/cancel` · `/retry` | Huỷ · chạy lại (tạo job mới) |
| GET / POST | `/api/worker` · `/api/worker/resume` | Trạng thái hàng đợi · tiếp tục sau khi tạm dừng |
| GET | `/api/search?q=&deep=1&tax_code=&ann_type=&date_from=&date_to=&pdf_only=1&page=` | Tìm bố cáo |
| GET | `/api/search/export.xlsx?...` | Xuất Excel với cùng bộ lọc |
| GET | `/api/announcements/{id}` | Chi tiết bố cáo (người đại diện, nhóm - khoá - giá trị) |
| GET | `/api/files/{id}[?download=1]` | File PDF: backend stream từ MinIO (giữ đăng nhập, không lộ địa chỉ/khoá MinIO ra trình duyệt) |
| GET | `/api/companies?q=` · `/api/companies/{mst}` | Doanh nghiệp · chi tiết kèm các khoảng đã crawl |
| GET | `/api/people?name=&id_number=&tax_code=` | Người đại diện theo pháp luật |

Thao tác ghi (POST) bắt buộc có header `X-Requested-With: XMLHttpRequest` (chống CSRF khi dùng mật khẩu Basic). Frontend đã tự gửi.

## Crawl hàng loạt từ file Excel

File mẫu (sheet `Input`, cùng định dạng tool Excel cũ) có các cột **Mã số thuế | Loại công bố | Từ ngày | Đến ngày | Crawl lại**
và sheet *Hướng dẫn*. Quy ước mỗi dòng:

| Cột | Nhận | Ví dụ |
|---|---|---|
| Mã số thuế | 10 hoặc 13 số, một mã mỗi dòng (ô kiểu số bị Excel ăn mất số 0 đầu thì tự bù lại) | `0101243150`, `0101243150-001` |
| Loại công bố | mã, tên loại, hoặc `ALL`; nhiều loại ngăn cách bằng `,` hoặc `;` | `AMEND`, `Đăng ký mới`, `AMEND,NEW`, `ALL` |
| Từ ngày / Đến ngày | `dd/MM/yyyy`, `yyyy-MM-dd` hoặc ô ngày của Excel; bỏ trống một hoặc cả hai đầu được | `01/01/2024` |
| Crawl lại | `Có` / `Không` (bỏ trống = Không) | `Có` |

Quy trình an toàn: **tải lên chỉ để xem trước**, không tạo job. Màn hình xem trước cho biết mỗi dòng hợp lệ hay lỗi (kèm lý do
và số dòng trong file), trùng với dòng khác, cần crawl hay đã có trong database (theo đúng quy tắc khoảng thời gian bên dưới).
Chỉ khi bấm *Crawl N cặp* mới tạo job, mỗi dòng giữ khoảng ngày riêng. Dòng lỗi bị bỏ qua, dòng trùng chỉ gửi một lần.
Giới hạn: file `.xlsx` tối đa 5 MB, 500 dòng và 1000 cặp (MST × loại) mỗi lần, vì mỗi cặp tốn một lượt captcha.
Các dòng trong cùng một file không "nhìn thấy" nhau khi xem trước, nên hai dòng chồng khoảng ngày có thể cùng báo "cần crawl";
khi gửi, dòng sau tự được rút gọn hoặc bỏ qua vì dòng trước đã giữ chỗ.

## Quy tắc "đã có thì không crawl" (khoảng thời gian)

Khoá một lần crawl là **(MST, loại công bố, khoảng ngày đăng)**. Logic ở `backend/app/coverage.py`, có 19 test.

1. **Chuẩn hoá khoảng yêu cầu.** Bỏ trống ngày = tất cả từ 01/01/2000 đến hôm nay. Nhập thiếu một đầu thì đầu thiếu là
   mốc đầu / hôm nay. "Đến ngày" ở tương lai bị cắt về hôm nay. Cả khoảng nằm trong tương lai thì không có gì để crawl.
2. **Khoảng đã có = các lần crawl thành công trước đó + các job đang chờ/đang chạy** (tránh hai người cùng gửi một yêu cầu).
3. **Ngày hôm nay chưa kết thúc**, còn có thể có bố cáo mới đăng sau lần crawl. Nên một lần crawl chỉ được coi là phủ
   tới *ngày crawl − 1*; riêng "hôm nay" chỉ được tính nếu vừa crawl trong vòng `TODAY_RECHECK_MINUTES` (mặc định 60) phút.
4. **Khoảng cần crawl = khoảng yêu cầu − khoảng đã có.**

| Tình huống | Hệ thống làm gì |
|---|---|
| Đã có trọn khoảng yêu cầu (trùng hoặc nằm trong khoảng đã crawl) | Ghi 1 job "Bỏ qua", **không crawl** |
| Có một phần (vd đã có 2024, hỏi 2024→2025) | Chỉ crawl phần thiếu (2025) |
| Thiếu nhiều đoạn rời nhau | Crawl **1 lần** cho đoạn bao ngoài (tốn 1 lượt captcha); bố cáo trùng không bị nhân đôi vì khoá duy nhất `(MST, loại, ngày giờ đăng)` |
| Không nhập ngày, lần trước đã crawl "tất cả" | Chỉ crawl các ngày mới từ lần trước đến nay |
| Tích *Bắt buộc crawl lại* | Bỏ qua kiểm tra, crawl đúng khoảng đã nhập, tải lại PDF |

**Chỉ ghi nhận "đã crawl" khi crawl thành công trọn vẹn** và trang trả về bảng kết quả hợp lệ (có dòng dữ liệu hoặc có hàng
tiêu đề cột). Crawl lỗi, bị huỷ, hoặc captcha sai khiến trang không trả bảng kết quả thì *không* ghi nhận, lần sau vẫn crawl lại.

## Chạy toàn bộ bằng Docker

Một lệnh build và chạy cả web (frontend + backend), MinIO; MySQL dùng cái có sẵn hoặc bật cái đi kèm:

```powershell
copy .env.example .env                 # điền MINIO_ACCESS_KEY / MINIO_SECRET_KEY, DATABASE_URL, APIKEY_2CAPTCHA
docker compose up -d --build           # lần đầu vài phút: build MinIO từ source, tải Chromium cho backend
# mở http://127.0.0.1:8080
docker compose --profile mysql up -d   # (tuỳ chọn) chạy thêm MySQL đi kèm, cổng 3307; DATABASE_URL mặc định đã trỏ vào nó
```

| Service | Làm gì | Cổng (chỉ 127.0.0.1) |
|---|---|---|
| `frontend` | build React rồi phục vụ bằng nginx, chuyển tiếp `/api` sang backend (cùng một địa chỉ nên đăng nhập và tải PDF chạy bình thường) | **8080** |
| `backend` | API + worker crawl (Chromium của Playwright) + tách PDF | 8000 (gỡ lỗi) |
| `minio` | lưu PDF, build từ `minio/Dockerfile` | 9000, console 9001 |
| `mysql` | chỉ chạy khi bật `--profile mysql` | 3307 |

Những điều khác biệt khi chạy trong container:
- **Database:** `DATABASE_URL` trong `.env` gốc. MySQL có sẵn trên máy chủ thì dùng host `host.docker.internal` (không phải `127.0.0.1`, vì đó là chính container).
- **Font cho bộ tách PDF:** bộ tách cần đúng 4 file Times New Roman của Windows (`times`, `timesbd`, `timesi`, `timesbi` `.ttf`). Compose mount chúng (chỉ đọc)
  từ `C:/Windows/Fonts`; máy khác đặt `PDF_FONT_DIR` trong `.env` trỏ tới thư mục chứa 4 file đó. Thiếu file thì `docker compose up` báo lỗi ngay thay vì tách sai.
  Không dùng font "tương thích" (Liberation Serif...) vì số thứ tự glyph khác, chữ sẽ bị giải mã sai.
- **Trình duyệt crawl:** Chromium của Playwright chạy có giao diện trên màn hình ảo Xvfb (`HEADLESS=false`, mặc định), vì reCAPTCHA hay chặn headless.
  Chưa kiểm chứng với trang bố cáo thật, như phần crawl nói chung.
- **Bảo mật:** các cổng chỉ mở cho máy này. Muốn máy khác truy cập: đặt `WEB_BIND=0.0.0.0` **và** `APP_USER` / `APP_PASSWORD` (dữ liệu có CCCD, địa chỉ cá nhân), nên đặt sau HTTPS.
- Dừng: `docker compose stop` (dữ liệu giữ nguyên). **Đừng** chạy `docker compose down -v`: lệnh này xoá volume MinIO (toàn bộ PDF) và MySQL đi kèm.
- Cập nhật sau khi sửa mã: `docker compose up -d --build backend frontend`.

## Lưu PDF trên MinIO

Backend **không giữ PDF trên đĩa**. Mỗi bố cáo crawl được xử lý như sau: tải PDF về thư mục tạm → tách nội dung → upload lên MinIO
→ ghi vào database → xoá file tạm. Database lưu vị trí file ở bảng `announcements`:

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `pdf_bucket` | bucket trên MinIO (rỗng = chưa có file trên MinIO) | `egazette` |
| `pdf_path` | object key trong bucket | `pdf/0101243150/AMEND/0101243150_AMEND_20260512_170600.pdf` |
| `pdf_size` | kích thước (byte) | `333658` |

Trang chi tiết bố cáo hiện `s3://bucket/key`, file Excel xuất ra có cột "File PDF (MinIO)". Xem PDF qua `/api/files/{id}`: backend đọc từ
MinIO rồi stream về, nên đăng nhập vẫn có tác dụng và trình duyệt không cần nói chuyện trực tiếp với MinIO.

**MinIO bằng docker compose:** service `minio` (build từ `minio/Dockerfile`, dữ liệu trong volume `egazette_minio_data`, chỉ lắng nghe `127.0.0.1`).
Key đặt trong file `.env` **ở thư mục gốc dự án** (cạnh `docker-compose.yml`, mẫu `.env.example`): `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`.
Compose và backend cùng đọc file này nên chỉ cần giữ một bản; container từ chối khởi động nếu thiếu key hoặc dùng key mặc định `minioadmin`.
Console quản trị: http://127.0.0.1:9001 (đăng nhập bằng access key / secret key). Đổi key: sửa `.env`, chạy
`docker compose up -d --force-recreate minio`, rồi khởi động lại backend. Đây là key quản trị (root); với môi trường thật nên vào console tạo
access key riêng chỉ có quyền trên bucket `egazette` và đặt vào `.env`.

**Cấu hình khác** trong `backend/.env`: `MINIO_ENDPOINT` (host:port, không kèm `http://`), `MINIO_BUCKET` (mặc định `egazette`, tự tạo nếu
chưa có), `MINIO_SECURE` (true nếu HTTPS). Dùng MinIO có sẵn của công ty thì đặt `MINIO_ENDPOINT` + hai key ngay trong `backend/.env`.

- **MinIO không kết nối được:** backend vẫn khởi động, xem/tìm kiếm dữ liệu bình thường; crawl **tạm dừng cả hàng đợi** với thông báo rõ ràng
  (bấm *Tiếp tục* sau khi MinIO chạy lại) và `/api/files` trả 502. Backend không cần khởi động lại.
- **Chuyển PDF cũ trên đĩa lên MinIO** (dữ liệu tạo bằng bản trước, có `pdf_path` nhưng chưa có `pdf_bucket`):
  ```powershell
  cd backend
  python -m app.migrate_pdfs --dry-run     # xem sẽ chuyển gì, không upload, không sửa database
  python -m app.migrate_pdfs               # upload + ghi pdf_bucket / pdf_size (chạy lại nhiều lần an toàn)
  python -m app.migrate_pdfs --delete-local   # (tuỳ chọn) xoá file cục bộ sau khi đã upload và kiểm tra đúng kích thước
  ```
  Thư mục nguồn là `LEGACY_STORAGE_DIR` (mặc định `backend/storage`) hoặc `--source`. Cho đến khi chuyển xong, các bố cáo cũ chưa có nút xem/tải PDF.
- **Database cũ** tự được thêm hai cột `pdf_bucket`, `pdf_size` khi backend khởi động (hoặc chạy tay hai lệnh `ALTER TABLE` ghi ở đầu `schema.sql`).
- **Image MinIO:** MinIO đã ngừng phát hành image / binary chính thức (Docker Hub, quay.io, dl.min.io đều báo lỗi) và repository đã archived, nên `minio/Dockerfile` build trực tiếp từ mã nguồn ở tag cố định `RELEASE.2025-10-15T17-29-55Z` (giấy phép AGPL-3.0). Bản này không còn nhận bản vá bảo mật: chỉ để máy nội bộ, đừng mở ra Internet. Đổi phiên bản: `docker compose build --build-arg MINIO_VERSION=<tag> minio`.

## Cấu trúc mã

```
backend/
├── run.py                  # chạy API + worker nền (waitress)
├── requirements.txt  .env.example  schema.sql
├── app/
│   ├── config.py db.py models.py
│   ├── coverage.py         # logic khoảng thời gian (hàm thuần)
│   ├── services.py         # đặt yêu cầu, lưu bố cáo, tìm kiếm
│   ├── web.py              # các endpoint /api (+ phục vụ frontend đã build)
│   ├── serializers.py      # đối tượng DB -> JSON
│   ├── crawler.py          # Playwright + 2captcha
│   ├── worker.py           # hàng đợi nền, 1 job tại một thời điểm
│   ├── pdf_parser.py       # giải mã & tách PDF thành key - value
│   ├── storage.py          # MinIO: upload / stream / kiểm tra file PDF (+ MemoryStore cho test)
│   ├── import_excel.py     # nhập dữ liệu từ tool Excel cũ (upload PDF lên MinIO)
│   └── migrate_pdfs.py     # chuyển PDF cũ trên đĩa lên MinIO
└── tests/                  # pytest
frontend/
├── vite.config.ts          # dev: chuyển tiếp /api -> backend (VITE_PROXY_TARGET)
└── src/
    ├── api.ts types.ts hooks.ts format.ts meta.tsx
    ├── components/         # Layout (thanh điều hướng + banner tạm dừng), Pager, StatusBadge...
    └── pages/              # Overview, Crawl, Jobs, Job, Search, Announcement, Companies, Company, People
```

Bảng chính: `crawl_jobs` (yêu cầu & trạng thái), `crawl_coverage` (khoảng đã crawl), `announcements` (bố cáo),
`announcement_fields` (toàn bộ nội dung PDF dạng nhóm - khoá - giá trị), `legal_reps` (người đại diện).
Vị trí file PDF nằm ở 3 cột của `announcements`: `pdf_bucket`, `pdf_path` (= object key) và `pdf_size`.

## Kiểm thử

```powershell
cd backend
pytest                                            # SQLite tạm
$env:TEST_DATABASE_URL="mysql+pymysql://egazette:egazette@127.0.0.1:3307/egazette?charset=utf8mb4"; pytest   # MySQL

cd ../frontend
npm run build       # kiểm tra kiểu TypeScript + build
npm test            # vitest
```
Test backend dùng **MinIO giả trong bộ nhớ** (không bao giờ chạm MinIO thật). Muốn chạy thêm các test với MinIO thật: đặt
`TEST_MINIO_ENDPOINT`, `TEST_MINIO_ACCESS_KEY`, `TEST_MINIO_SECRET_KEY` (mỗi test tự tạo bucket tạm `egazette-test-…` rồi xoá).
Test backend toàn luồng dùng **crawler giả** (lọc theo ngày như trang thật, "tải" PDF mẫu), không gọi trang bố cáo và không tốn
tiền 2captcha. Các test cần PDF mẫu đọc từ `SAMPLE_PDF_DIR` (mặc định thư mục output của tool cũ), thiếu thì tự bỏ qua.

## Triển khai

- **Một địa chỉ (khuyến nghị):** build frontend, chạy `python run.py`. Có mật khẩu (`APP_USER`/`APP_PASSWORD`) thì trình duyệt
  hỏi một lần và tự dùng lại cho cả API lẫn file PDF.
- **Hai địa chỉ:** host `frontend/dist` ở nơi khác (Nginx, CDN...), build với `VITE_API_URL=https://api...`, và đặt
  `CORS_ORIGINS=https://app...` ở backend. Cách này không hợp với mật khẩu Basic (trình duyệt không hỏi mật khẩu cho
  yêu cầu cross-origin); nếu cần đăng nhập, đặt cả hai sau một reverse proxy cùng domain (`/` → frontend, `/api` → backend).

## Cần biết

- **Phần crawl thật chưa được kiểm chứng trong dự án này**: logic điền form / giải captcha / đọc bảng / tải PDF lấy từ tool Excel cũ
  (đã chạy được), nhưng chưa chạy qua giao diện web. Nên chạy thử 1 MST nhỏ trước.
- Cần kiểm tra thực tế: trang có tính bố cáo của **đúng ngày "Đến ngày"** hay không (thử `từ = đến = một ngày đã biết có bố cáo`).
  Nếu không, cần cộng thêm 1 ngày khi điền ô "Đến ngày" trong `backend/app/crawler.py`.
- Kết quả 0 dòng mà trang không có hàng tiêu đề được coi là *chưa xác nhận* (job "Xong (có lưu ý)", không ghi nhận đã crawl).
- Mỗi lần crawl tốn 1 lượt giải captcha trên 2captcha. Hết số dư / sai key thì hàng đợi tự dừng.
- Dữ liệu có **CCCD và địa chỉ cá nhân**. Mở cho nhiều người dùng: đặt `HOST=0.0.0.0` *và* `APP_USER`/`APP_PASSWORD`
  (HTTP Basic, nên đặt sau HTTPS). Hiện chưa phân quyền theo người dùng.
- Bảng cổ phần / cổ đông trong PDF không được tách (số liệu bị dính ô).
- Chỉ có 1 worker nên các job chạy lần lượt. Chạy nhiều tiến trình backend thì chỉ để 1 tiến trình bật worker (`START_WORKER=false` cho các tiến trình còn lại).
