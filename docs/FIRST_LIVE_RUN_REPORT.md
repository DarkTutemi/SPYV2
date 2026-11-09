# US WIN HUNTER — Báo Cáo Kiểm Tra Tiền Khởi Chạy Sống Đầu Tiên (First Live Run Pre-Flight Report)

Tài liệu này xác nhận trạng thái sẵn sàng vận hành, hợp đồng kỹ thuật và các chốt chặn an toàn được thiết lập trước khi thực hiện lần quét dữ liệu sống đầu tiên trên nền tảng Apify Meta Ad Library.

---

## 1. Trạng Thái Vận Hành Sống (Live Execution Status)

- **Trạng thái bộ chuyển đổi (Adapter Status)**: `READY` (Đã cấu hình token thành công — Chờ lệnh ủy quyền chạy từ người vận hành)
- **Tự động thu thập trả phí (Paid Auto-Collection)**: `DISABLED` (`apify_auto_collection_enabled = False`)
- **Ngân sách ngày / tháng**: `$2.00 USD / ngày`, `$10.00 USD / tháng`
- **Khóa ủy quyền vận hành (Operator Authorization Gate)**: `LOCKED` (Chưa có lệnh ủy quyền chạy trực tiếp từ người vận hành)
- **Rào cản ngân sách đa tiến trình (Budget Concurrency)**: `ACTIVE` (Đặt chỗ ngân sách nguyên tử trên cơ sở dữ liệu SQLite WAL)

---

## 2. Đặc Tả Đợt Thu Thập Giới Hạn Đầu Tiên (Prepared First Bounded Test Run)

Cấu hình đợt thu thập sống đầu tiên đã được đóng băng và kiểm định:

| Tham Số | Giá Trị Cố Định | Ý Nghĩa Kỹ Thuật |
| :--- | :--- | :--- |
| **Actor định danh** | `automation-lab/facebook-ads-library` | Actor chính thức duy nhất, tắt hoàn toàn fallback |
| **Thị trường mục tiêu** | `country = "US"` | Lọc chặt chẽ quảng cáo thương mại tại Hoa Kỳ |
| **Từ khóa hạt giống** | `"washable microfiber mop pads"` | Sản phẩm tiêu dùng vật lý có nhu cầu thay thế, dùng theo bộ |
| **Trạng thái quảng cáo**| `activeStatus = "active"` | Chỉ lấy các chiến dịch đang hoạt động (*lowercase* chuẩn schema) |
| **Thứ tự thu thập** | `sortBy = "recent"` | Thu thập theo thời gian thực để đón sóng đà sớm |
| **Giới hạn số lượng** | `maxAds = 20` | Khống chế tối đa 20 bản ghi trên lượt quét |
| **Trần chi phí lượt chạy**| `maxTotalChargeUsd = 0.50` | Tham số ngắt tức thì trên hạ tầng đám mây Apify |
| **Chu kỳ lặp lại** | `is_recurring = False` | Đơn lẻ một lần, không kích hoạt lịch trình |

---

## 3. Chỉ Số Dữ Liệu Hiện Tại Trong Hệ Thống (Repository Audit Baseline)

Tại thời điểm trước khi người vận hành kích hoạt đợt cào dữ liệu sống:

| Hạng Mục | Số Lượng Hiện Tại | Bản Chất Dữ Liệu & Nguồn Gốc |
| :--- | :--- | :--- |
| **Bản ghi quảng cáo US thật đã xác minh (Verified Live US Ads)** | **0** | Chưa có lệnh gọi API thật ra bên ngoài |
| **Nhà quảng cáo duy nhất thực tế (Unique Real Advertisers)** | **0** | Cơ sở dữ liệu production hoàn toàn sạch |
| **Sản phẩm trích xuất từ dữ liệu thật (Real Extracted Products)** | **0** | Không có sản phẩm thật trong DB |
| **Ứng viên Combo tự nhiên (Natural-Bundle Candidates)** | **0 (Live) / 3 (Fixtures)** | Bộ test dùng fixture kiểm thử thuật toán |
| **Liên kết nguồn hợp lệ (Valid Source Links)** | **0 (Live)** | Không có link landing page nào được cào sống |
| **Chi phí đã thanh toán thực tế (Actual Billed Charges)** | **$0.0000 USD** | Chưa phát sinh bất kỳ khoản phí nào |
| **Lỗi phân tích cú pháp (Parsing Failures)** | **0** | Không có dữ liệu rác hay lỗi phân tích |

---

## 4. Bốn Cơ Chế Gia Cố Pre-Live Hoàn Thành

### 4.1. Đặt Chỗ Ngân Sách Nguyên Tử (Persistent Atomic Budget Reservation)
- Thay thế cơ chế khóa trong bộ nhớ `asyncio.Lock` bằng cơ chế **cam kết ngân sách nguyên tử trên CSDL** (`reserve_budget`).
- Trước khi gửi request sang Apify, hệ thống tạo bản ghi `CollectionRun` với trạng thái `RUNNING` và cam kết chi phí dự phòng `reserved_cost_usd = 0.50`.
- Bất kỳ tiến trình FastAPI worker, scheduler hoặc CLI nào chạy song song đều đọc cam kết này từ CSDL và bị chặn ngay lập tức nếu tổng chi phí cam kết vượt ngưỡng `$5.00/ngày` hoặc `$50.00/tháng`.
- Tự động dọn dẹp các run mồ côi (stale runs > 15 phút) chuyển sang `FAILED` để không làm nghẽn ngân sách.

### 4.2. Thanh Toán Đa Tầng Pay-Per-Event (Apify PPE Billing Extraction)
- Phương thức `extract_billing_details` bóc tách độc lập:
  - `usageTotalUsd`: Chi phí điện toán nền tảng (CU, Proxy, Memory)
  - `eventUsageTotalUsd`: Chi phí trả theo sự kiện (Pay-Per-Event, ví dụ: 20 ads * $0.0012)
  - `chargedTotalUsd`: Tổng hóa đơn thực do Apify ghi nhận
  - `chargedEventCounts`: Số lượng sự kiện cào được tính tiền
- Phân định minh bạch:
  - `VERIFIED_CHARGED`: Chi phí thật có hóa đơn từ provider (`> $0.00`).
  - `ESTIMATED`: Chi phí ước tính cục bộ nếu provider trả về unmetered.
  - `UNMETERED`: Lượt chạy thử nghiệm không mất phí ($0.00).

### 4.3. Phân Lớp Độ Tươi Quảng Cáo (Ad Launch Freshness vs Activity)
- Phân biệt rạch ròi giữa thời điểm hệ thống lần đầu quan sát thấy quảng cáo (`first_seen_at`) và ngày nhà quảng cáo bắt đầu chạy chiến dịch trên Meta (`advertiser_start_date` / `startDate`).
- Không nhầm lẫn các chiến dịch thường niên đã chạy hàng trăm ngày (`ESTABLISHED_CAMPAIGN`) với các sản phẩm mới nổi:
  - `NEW_LAUNCH_7D`: Khởi chạy trong vòng 7 ngày gần nhất.
  - `NEW_LAUNCH_14D`: Khởi chạy trong vòng 14 ngày.
  - `NEW_LAUNCH_30D`: Khởi chạy trong vòng 30 ngày.
  - `ESTABLISHED_CAMPAIGN`: Đã chạy trên 30 ngày (sản phẩm cũ/bão hòa).
- Phương thức `filter_by_launch_window(records, max_days=30)` cho phép tách riêng sản phẩm mới nổi trước khi đưa vào chấm điểm cơ hội.

### 4.4. Phân Định Bằng Chứng Địa Lý Hoa Kỳ (US Evidence Separation)
- `EXPLICIT_US_TARGETING` (`HIGH` Confidence): Nhà quảng cáo chủ động chọn nhắm mục tiêu US.
- `OBSERVED_US_DELIVERY` (`HIGH` Confidence): Số liệu phân phối hiển thị ghi nhận người dùng tại các bang US.
- `US_SEARCH_FILTER` (`MEDIUM` Confidence): Quảng cáo thu thập từ bộ lọc `country="US"` của Meta nhưng không có báo cáo nhân khẩu học. **Tuyệt đối không gán mác là nhắm mục tiêu đã xác nhận**.
- `NON_US_TARGETING` (`REJECTED`): Quảng cáo nhắm mục tiêu rõ ràng ngoài US -> Loại bỏ ngay tại cổng kiểm định.

---

## 5. Rào Cản Kỹ Thuật Còn Lại Trước Khi Chạy Thật (Remaining Blockers)

1. **Khóa API Apify (`APIFY_API_TOKEN`)**:
   - **ĐÃ CẤU HÌNH XONG**: Đã tạo file `.env` từ `.env.example` với mã token, hạn mức ngày `$2.00`, hạn mức tháng `$10.00`, và auto-collection `false`.
2. **Lệnh Ủy Quyền Tường Minh Của Người Vận Hành (Operator Approval)**:
   - **ĐANG CHỜ ỦY QUYỀN**: Hệ thống được cấu hình fail-closed. Không có bất kỳ lệnh gọi trả phí nào được phép tự động khởi phát cho đến khi người vận hành ra lệnh bằng văn bản hoặc gọi endpoint xác nhận.

