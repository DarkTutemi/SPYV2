# BẢNG ĐẶC TẢ CẤU HÌNH GIÁM SÁT T+14 HOÀN THIỆN — US WIN HUNTER
**US WIN HUNTER — FINAL T+14 MONITORING CONFIGURATION SPECIFICATION**

- **Hệ thống:** US WIN HUNTER — Intelligence Orchestrator
- **Mã định danh tác vụ:** `T14-MONITORING-OPS-20261124`
- **Mốc thời gian kích hoạt cho phép:** **Sau 01:26:00 ngày 24/11/2026 (Giờ Việt Nam / ICT, UTC+7)**
- **Nhà cung cấp:** Apify (`automation-lab/facebook-ads-library`)
- **Tình trạng phê duyệt hiện tại:** **PENDING OPERATOR APPROVAL (CHỜ LỆNH PHÊ DUYỆT)**
- **Khóa an toàn:** `APIFY_AUTO_COLLECTION_ENABLED=false` duy trì nghiêm ngặt.

---

## 1. BẢNG XÁC THỰC 6 TRANG NHÀ BÁN HÀNG VÀ MÃ QUẢNG CÁO MỤC TIÊU

| Thứ hạng | Cơ hội sản phẩm | Nhà bán hàng đại diện | Facebook Page ID (Xác thực 100%) | Mã Ad Archive ID T0 gốc | Tên miền cửa hàng | Mốc quan sát T0 gốc (UTC) |
| :---: | :--- | :--- | :---: | :---: | :--- | :---: |
| **#1** | Reusable Washable Dog Pee Pads | Diego's Paws | `1294258113779496` | `1654383812796911` | `diegospaws.com` | 2026-11-09 18:23:45 |
| **#2** | Men's Leakproof Boxers | Prostate Warriors (Menvault) | `122094798914008278` | `1135373669505006` | `menvault.com` | 2026-11-09 18:22:55 |
| **#3** | Replacement Spin Mop Heads | Swiftlifty | `1427580890438766` | `1822961982334971` | `swiftlifty.com` | 2026-11-09 15:08:19 |
| **#4** | Silicone Chair Leg Protectors | AlexCove | `1254199584442968` | `1441655818106115` | `alexcove.com` | 2026-11-09 18:24:22 |
| **#5** | Microfiber Car Detailing Towels | Tremendousup (Novtris) | `889767694223771` | `1385909230286911` | `novtris.com` | 2026-11-09 18:23:27 |
| **#6** | Rubber Anti-Curling Rug Grippers | Gridsparkl/er | `1238627265989998` | `1102527249449007` | `gridsparkl.com` | 2026-11-09 18:25:37 |

---

## 2. XÁC NHẬN CƠ CHẾ KỸ THUẬT VÀ PHÍ NHÀ CUNG CẤP

### 1. Tính độc lập của đầu vào (Failure Isolation):
- Tài liệu chính thức của Actor quy định: *"Skipped inputs, including non-Facebook or non-Page URLs, get a status message and are never charged. ... Ads from all sources will be combined."*
- Nếu một Page bất kỳ gặp sự cố (ví dụ bị xóa trang hoặc 0 quảng cáo), worker của Actor sẽ ghi cảnh báo và tiếp tục cào các Page còn lại vào cùng một Dataset. Kết quả của các Page thành công không bị hủy bỏ.

### 2. Định mức chi phí và Giới hạn trần cứng:
- **Mô hình tính phí:** Pay-Per-Event (Apify Free Tier)
  - Phí khởi tạo phiên cào (`start` event): **$0.0050 USD**
  - Phí trích xuất mỗi quảng cáo (`ad-scraped` event): **$0.000575 USD**
- **Định mức số lượng:** 6 Pages $\times$ tối đa 20 ads/Page = **120 quảng cáo tối đa**.
- **Chi phí kịch bản tối đa (Worst-case charge):**
  $$\text{Chi phí tối đa} = \$0.0050 + (120 \times \$0.000575) = \$0.0050 + \$0.0690 = \mathbf{\$0.0740\text{ USD}}$$
- **Giới hạn ngân sách khóa cứng (Hard Spending Cap):** **$0.0800 USD**.
  $$\$0.07400 \le \$0.08000 \implies \mathbf{ĐẢM\ BẢO\ 100\%\ KHÔNG\ BAO\ GIỜ\ VƯỢT\ TRẦN}$$

---

## 3. PAYLOAD CHÍNH THỨC CỦA LƯỢT CHẠY DUY NHẤT (COMBINED RUN PAYLOAD)

```json
{
  "pageUrls": [
    "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id=1294258113779496",
    "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id=122094798914008278",
    "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id=1427580890438766",
    "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id=1254199584442968",
    "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id=889767694223771",
    "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&view_all_page_id=1238627265989998"
  ],
  "country": "US",
  "activeStatus": "all",
  "sortBy": "recent",
  "mediaType": "all",
  "maxAds": 20
}
```

---

## 4. QUY CHUẨN ĐỐI SOÁT BẰNG CHỨNG TRẠNG THÁI (STRICT MATCHING TAXONOMY)

- **`OBSERVED_ACTIVE`**: Quảng cáo mục tiêu có trong Dataset VÀ `isActive == true`.
- **`OBSERVED_INACTIVE`**: Quảng cáo mục tiêu có trong Dataset VÀ `isActive == false` (hoặc có ngày kết thúc `endDate`).
- **`UNKNOWN (ABSENT_FROM_WINDOW)`**: Quảng cáo mục tiêu KHÔNG xuất hiện trong tối đa 20 quảng cáo trả về của Page.
  - *Lý giải:* Cửa sổ phân trang bị giới hạn ở 20 quảng cáo gần nhất; không đủ bằng chứng để khẳng định quảng cáo đã tắt.
- **`ACCESS_ERROR`**: Bị lỗi kết nối, lỗi proxy hoặc gateway của nhà cung cấp.

---

## 5. PHƯƠNG ÁN TUẦN TỰ DỰ PHÒNG (BOUNDED SEQUENTIAL ALTERNATIVE)

Nếu Operator muốn cô lập 100% rủi ro của từng Page thành 6 tác vụ độc lập:
- 6 Runs tuần tự, mỗi Run cào 1 Page duy nhất (`maxAds: 20`).
- Giới hạn cứng từng Run: `maxTotalChargeUsd: 0.0170 USD`.
- Tổng chi phí dự toán: $(6 \times \$0.0050) + (120 \times \$0.000575) = \mathbf{\$0.0990\text{ USD}}$.
- *Đánh giá:* Chi phí cao hơn phương án chạy gộp $0.025 USD do phát sinh 6 lần phí khởi tạo `start`. **Chỉ thực thi khi có sự chỉ đạo riêng từ Operator**.

---

*Tài liệu được khởi tạo tự động bởi US WIN HUNTER — Intelligence Orchestrator.*

