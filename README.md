# map-crawler

`map-crawler` là công cụ Python dùng Selenium để thu thập dữ liệu địa điểm từ kết quả tìm kiếm Google Maps. Dự án phù hợp khi cần tạo danh sách khách sạn, nhà hàng, điểm tham quan, dịch vụ du lịch hoặc doanh nghiệp địa phương theo từng khu vực.

Công cụ có cả giao diện GUI bằng Tkinter và chế độ dòng lệnh. Dữ liệu có thể xuất ra CSV, JSONL, SQLite hoặc Excel, kèm các thông tin như tên địa điểm, danh mục, địa chỉ, quận/huyện, tỉnh/thành, tọa độ, rating, số đánh giá, giá, số điện thoại, website và link Google Maps.

## Tên Dự Án

Tên hiển thị:

```text
map-crawler
```

Tên repository GitHub:

```text
map-crawler
```

## Tính Năng Chính

- Chạy bằng GUI để tạo job, chọn danh mục, xem preview và theo dõi log.
- Chạy bằng CLI cho workflow tự động hóa hoặc crawl nhanh một query.
- Tạo nhiều job từ danh sách loại địa điểm, từ khóa và khu vực.
- Import job từ TXT/CSV và lưu preset cấu hình.
- Chọn trường dữ liệu cần xuất.
- Xuất CSV, JSONL, SQLite hoặc Excel `.xlsx`.
- Ghi file sau khi crawl xong hoặc ghi từng dòng trong lúc crawl.
- Resume từ checkpoint/output cũ và chống trùng lặp theo `destination_id`, `name_address` hoặc `coordinates`.
- Tách output theo danh mục hoặc location.
- Lưu report crawl, failed rows và screenshot khi gặp lỗi.

## Yêu Cầu

- Python 3.10+.
- Google Chrome đã cài trên máy.
- Kết nối internet ổn định.

Selenium thường có thể tự quản lý driver phù hợp với Chrome. Nếu Selenium báo lỗi driver, hãy cài ChromeDriver tương ứng với phiên bản Chrome đang dùng và đảm bảo `chromedriver` nằm trong `PATH`.

## Cài Đặt

Clone repository:

```powershell
git clone https://github.com/<username>/map-crawler.git
cd map-crawler
```

Tạo môi trường ảo:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Cài dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Chạy Bằng GUI

Mở ứng dụng:

```powershell
python google_maps_gui.py
```

Trong GUI, bạn có thể:

1. Chọn loại địa điểm, ví dụ `khách sạn`, `nhà hàng`, `resort`.
2. Nhập location, ví dụ `Đà Nẵng`, `Hội An`, `Quận 1`.
3. Đặt số lượng kết quả mỗi job.
4. Chọn file output và định dạng xuất.
5. Bấm `Thêm job` hoặc `Tạo từ multi query`.
6. Bấm `Start` để bắt đầu crawl.

## Chạy Bằng CLI

Ví dụ crawl 20 khách sạn ở Đà Nẵng và xuất CSV:

```powershell
python crawl_google_maps_selenium.py "khách sạn Đà Nẵng" --limit 20 --out data/hotels_da_nang.csv
```

Chạy ẩn Chrome:

```powershell
python crawl_google_maps_selenium.py "nhà hàng Hội An" --limit 50 --headless --out data/restaurants_hoi_an.csv
```

Xuất Excel:

```powershell
python crawl_google_maps_selenium.py "resort Phú Quốc" --limit 30 --export-format xlsx --out data/resorts_phu_quoc.xlsx
```

Resume và chống trùng lặp:

```powershell
python crawl_google_maps_selenium.py "quán cà phê Đà Nẵng" --limit 100 --resume --dedupe-mode destination_id --out data/cafes_da_nang.csv
```

Chỉ xuất một số trường:

```powershell
python crawl_google_maps_selenium.py "spa Huế" --limit 30 --fields name,address,rating,phone,website,maps_url --out data/spa_hue.csv
```

## Import Job

GUI hỗ trợ import job từ file TXT hoặc CSV.

TXT có thể dùng các dạng sau:

```text
khách sạn|Đà Nẵng|50
nhà hàng|đặc sản|Hội An|30|data/restaurants_hoi_an.csv
```

CSV nên có các cột:

```csv
type,keyword,location,limit,output
khách sạn,view biển,Đà Nẵng,50,data/hotels_da_nang.csv
spa,,Huế,20,data/spa_hue.csv
```

## Output

Mặc định schema gồm các trường:

```text
name, normalized_name, category, destination_id, address, province, district, ward,
description, price_min, price_max, price_text, rating, review_count, latitude,
longitude, image_url, maps_url, phone, website, open_hours,
estimated_duration_minutes, suitable_time, tags, source_count, confidence_score,
created_at, updated_at
```

Ngoài file output chính, quá trình crawl có thể tạo thêm:

- `*_checkpoint.json`: đánh dấu URL đã xử lý để resume.
- `*_failed_rows.csv`: các dòng crawl lỗi.
- `*_crawl_report.json`: thống kê số dòng đã lưu, số lỗi và trường bị thiếu.
- `screenshots/`: ảnh chụp màn hình khi gặp lỗi crawl.

## Chạy Test

```powershell
python -m unittest discover -s tests
```

## Lưu Ý Sử Dụng

Tool này không thêm proxy, stealth hay bypass CAPTCHA. Nếu Google chặn phiên crawl, hãy giảm số lượng job, tăng delay, tắt song song hoặc cân nhắc dùng Google Places API chính thức cho workflow sản xuất.

Hãy chỉ crawl dữ liệu bạn có quyền sử dụng và tuân thủ điều khoản của dịch vụ/website liên quan.
