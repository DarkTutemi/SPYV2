# BÁO CÁO TIỀN KIỂM SOÁT HỢP ĐỒNG ĐƠN VỊ THU THẬP T+14 — US WIN HUNTER
**US WIN HUNTER — T+14 MONITORING PROVIDER CONTRACT CHECK**

- **Hệ thống:** US WIN HUNTER — Intelligence Orchestrator
- **Mục tiêu:** Thẩm định hợp đồng đầu vào chính thức của Actor thu thập Meta Ads, rà soát giới hạn kỹ thuật của Meta Graph API và lập kế hoạch thực thi giám sát độ sinh tồn T+14 (23–24/11/2026) với chi phí nhỏ nhất có căn cứ.
- **Tuân thủ kỷ luật vận hành:**
  - Tuyệt đối **KHÔNG** chạy Actor trả phí nào trước T+14 (`APIFY_AUTO_COLLECTION_ENABLED=false`).
  - Tuyệt đối **KHÔNG** vượt rào truy cập, không bypass CAPTCHA.
  - Tuyệt đối **KHÔNG** tự ý giả định tính năng nếu chưa được tài liệu hóa chính thức từ nhà cung cấp.
- **Tình trạng kiểm thử hồi quy:** Đã bổ sung bộ kiểm thử `backend/tests/test_t14_preflight.py` (5/5 passed). Toàn bộ hệ thống: **126 / 126 bài kiểm tra đạt 100% Passed**.

---

## 1. BẢNG TỔNG HỢP KẾT QUẢ TIỀN KIỂM SOÁT (EXECUTIVE PREFLIGHT DASHBOARD)

| Hạng mục kiểm tra | Kết quả thẩm định | Phân loại trạng thái | Căn cứ tài liệu kỹ thuật & Bằng chứng nguồn |
| :--- | :---: | :---: | :--- |
| **Hỗ trợ tra cứu trực tiếp theo Ad Archive ID** | **KHÔNG HỖ TRỢ (UNSUPPORTED)** | **EXACT_ID_LOOKUP_UNSUPPORTED** | Tài liệu chính thức của Actor khẳng định rõ: *"Single-ad links (`?id=...`) are skipped with a warning; paste the search results URL or the advertiser Page URL instead."* |
| **Phương thức theo dõi có căn cứ được hỗ trợ** | **TÌM THEO FACEBOOK PAGE ID** | **SUPPORTED & PROVEN** | Actor hỗ trợ đầy đủ `pageUrls` và `view_all_page_id`. Đã lưu trữ 100% Page ID của 6 nhà bán hàng trong Watchlist. |
| **Khả năng sử dụng Meta Graph API chính thức** | **BỊ CHẶN BỞI META (BLOCKED)** | **RESTRICTED TO EU/UK** | Meta Ad Library API chính thức áp dụng "bức tường địa lý": Chỉ mở quảng cáo thương mại cho EU/UK theo đạo luật DSA; quảng cáo thương mại tại thị trường Mỹ (US) bị chặn hoàn toàn. |
| **Chi phí dự toán thực tế nhỏ nhất** | **$0.0395 – $0.0645 USD** | **DƯỚI 7 XU MỸ** | - 1 lượt chạy gộp 6 Page: **~$0.0395 USD**.<br/>- 6 lượt chạy cô lập: **~$0.0645 USD**.<br/>- Hạn mức trần an toàn khóa cứng: **$0.0800 USD**. |
| **Mốc thời gian đo kiểm T+14 đề xuất** | **23/11 & 24/11/2026** | **2 COHORT BASELINE** | - Cohort 1 (20 ads Phase 7): **23/11/2026**.<br/>- Cohort 2 (125 ads Phase 10): **24/11/2026** (theo giờ ICT địa phương). |
| **Yêu cầu chạy test trả phí trước T+14** | **HOÀN TOÀN KHÔNG CẦN THIẾT** | **ZERO TEST SPEND** | Hợp đồng input đã được xác minh qua schema v0.1 và dữ liệu thực tế Task 13, 14 của Phase 10. |

---

## 2. NHIỆM VỤ 1 — THẨM ĐỊNH TÍNH NĂNG TRA CỨU AD ARCHIVE ID TRỰC TIẾP

### 1. Phân tích Schema và Hợp đồng đầu vào (Input Contract):
Hệ thống đã truy vấn trực tiếp schema phiên bản mới nhất (`v0.1`, Build `RbzHZOgC2D5vvhph0`) của Actor `automation-lab/facebook-ads-library`:
- Các trường đầu vào được định nghĩa: `searchQueries`, `pageUrls`, `adsLibraryUrls`, `country`, `activeStatus`, `mediaType`, `onlyAdsNewerThan`, `onlyAdsOlderThan`, `searchType`, `sortBy`, `maxAds`, `includeAdDetails`.
- **Hoàn toàn KHÔNG CÓ trường `adArchiveIds` hay `adIds`.**
- Trong mô tả của trường `adsLibraryUrls`, Actor nêu rõ:
  > *"Paste Facebook Ads Library results URLs copied from facebook.com/ads/library/. Embedded URL filters (keyword, page ID, country, status, media type, search type, and supported ad type) are used for this input; unsupported URL parameters such as date, language, or platform filters are ignored with a warning."*

### 2. Căn cứ từ tài liệu hướng dẫn chính thức (Actor Readme):
Trong tệp tài liệu kỹ thuật dài 27.732 ký tự của Actor, nhà phát triển quy định minh thị:
> **"A URL needs a keyword (`q`) or advertiser (`view_all_page_id`) filter. Single-ad links (`?id=...`) are skipped with a warning; paste the search results URL or the advertiser Page URL instead."**

### 3. Kết luận phân loại:
$$\mathbf{EXACT\_ID\_LOOKUP\_UNSUPPORTED}$$
- **Rủi ro nếu vi phạm:** Nếu truyền URL dạng `https://www.facebook.com/ads/library/?id=1654383812796911` vào Actor, scraper sẽ tự động bỏ qua (skip), cảnh báo lỗi, không trả về dữ liệu nhưng vẫn trừ phí khởi chạy ($0.0050 USD/run).
- **Hành động cấm:** Tuyệt đối không chuẩn bị hoặc khởi chạy bất kỳ lượt chạy Apify nào dùng ID đơn lẻ với Actor này.

---

## 3. NHIỆM VỤ 2 — ĐÁNH GIÁ PHƯƠNG THỨC GIÁM SÁT THEO TRANG NHÀ QUẢNG CÁO (ADVERTISER PAGE MONITORING)

Do việc tra cứu theo ID trực tiếp không được hỗ trợ, phương thức giám sát duy nhất có căn cứ dữ liệu là **Truy vấn theo Facebook Page ID của nhà bán hàng (`pageUrls` hoặc `view_all_page_id`)**.

### Bảng đối soát 6 Facebook Page ID thực tế trong Cơ sở dữ liệu:

| Thứ hạng | Cơ hội sản phẩm | Ad ID mục tiêu | Nhà bán hàng đại diện | Facebook Page ID (Xác thực 100%) | Trạng thái Domain |
| :---: | :--- | :---: | :--- | :---: | :--- |
| **#1** | Thảm vệ sinh cún giặt lại | `1654383812796911` | Diego's Paws | `1294258113779496` | `diegospaws.com` (Active) |
| **#2** | Quần lót nam chống rò | `1135373669505006` | Prostate Warriors (Menvault) | `122094798914008278` | `menvault.com` (Active) |
| **#3** | Đầu lau xoay 360° | `1822961982334971` | Swiftlifty | `1427580890438766` | `swiftlifty.com` (Active) |
| **#4** | Nút bọc chân ghế silicone | `1441655818106115` | AlexCove | `1254199584442968` | `alexcove.com` (Active) |
| **#5** | Khăn microfiber lau xe | `1385909230286911` | Tremendousup (Novtris) | `889767694223771` | `novtris.com` (Active) |
| **#6** | Miếng dán chống quăn thảm | `1102527249449007` | Gridsparkl/er | `1238627265989998` | `gridsparkl.com` (Active) |

### Cơ chế khớp mã quảng cáo (Exact Matching Mechanism):
1. **Đầu vào truy vấn:** Sử dụng `pageUrls: ["1294258113779496", ...]` kết hợp bộ lọc thị trường Mỹ (`country: "US"`, `activeStatus: "all"`, `sortBy: "recent"`, `maxAds: 10`).
2. **Khớp mã:** Quét mảng kết quả trả về, đối soát trường `adArchiveId` với mã quảng cáo mục tiêu đã lưu tại T0.
3. **Cấm thay thế:** Không bao giờ lấy quảng cáo mới của nhà bán hàng để thay thế cho quảng cáo mục tiêu đã mất dấu.
4. **Phân biệt ranh giới:** Không đánh đồng "không thấy trong kết quả giới hạn" là "quảng cáo đã tắt".

---

## 4. NHIỆM VỤ 3 — QUY CHUẨN XÁC ĐỊNH BẰNG CHỨNG TRẠNG THÁI (STATUS EVIDENCE RULES)

Để đảm bảo tính khách quan khoa học, hệ thống thiết lập bảng phân định 5 trạng thái:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ QUY TẮC PHÂN LOẠI TRẠNG THÁI QUAN SÁT T+14:                                                                      │
├──────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┤
│ Trạng thái               │ Điều kiện xác thực bắt buộc                                                           │
├──────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
│ OBSERVED_ACTIVE          │ Bản ghi trả về từ Apify có adArchiveId trùng khớp mục tiêu VÀ isActive == true.       │
│ OBSERVED_INACTIVE        │ Bản ghi trả về có adArchiveId trùng khớp mục tiêu VÀ isActive == false (có endDate).  │
│ ACCESS_ERROR             │ HTTP 403, lỗi proxy, bị chặn gateway hoặc lỗi kết nối nhà cung cấp.                  │
│ NOT_FOUND                │ Toàn bộ trang của nhà bán hàng bị xóa (Page not found 404).                          │
│ UNKNOWN                  │ Ad mục tiêu KHÔNG xuất hiện trong số maxAds trả về từ Page.                           │
│ (ABSENT_FROM_WINDOW)     │ Lý do: Cửa sổ cào bị cắt ngắn (truncation), ad bị đẩy lùi bởi các ad mới hơn.         │
└──────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Nguyên tắc phủ định (Negative Evidence Principle):**  
> Việc một quảng cáo không xuất hiện trong 10 quảng cáo được cào về từ một Page có thể chỉ do cửa sổ phân trang bị giới hạn (`maxAds = 10`), không chứng minh được quảng cáo đó đã ngừng hoạt động. Chỉ ghi nhận `OBSERVED_INACTIVE` khi có bằng chứng rõ ràng (như nhãn Inactive hoặc ngày kết thúc cụ thể).

---

## 5. NHIỆM VỤ 4 — GIỚI HẠN KỸ THUẬT CỦA META AD LIBRARY GRAPH API CHÍNH THỨC

Một câu hỏi quan trọng là: *Tại sao không dùng trực tiếp API chính thức của Meta (Graph API) thay vì dùng Apify?*

### Kết quả điều tra thực tế chính sách & kỹ thuật của Meta:
1. **Quảng cáo Chính trị / Bầu cử / Xã hội (`POLITICAL_AND_ISSUE_ADS`):**
   - Hỗ trợ toàn cầu qua endpoint `ads_archive`. Yêu cầu xác thực danh tính cá nhân nhà phát triển.
2. **Quảng cáo Thương mại Thông thường (`ALL`):**
   - **Bức tường địa lý (The Geographic Country Wall):** Do áp lực của Đạo luật Dịch vụ Kỹ thuật số (DSA), Meta chỉ mở quyền truy vấn dữ liệu quảng cáo thương mại thông thường cho **các quốc gia thành viên Liên minh Châu Âu (EU) và Vương quốc Anh (UK)**.
   - **Thị trường Hoa Kỳ (United States):** Nếu tham số `country` hoặc `ad_reached_countries` được đặt là `"US"`, API Meta sẽ trả về kết quả rỗng (`[]`) hoặc báo lỗi phân quyền.
3. **Kết luận:**  
   Quyền truy cập Meta Developer thông thường **KHÔNG PHẢI** là quyền truy cập không giới hạn. Meta cố tình chặn việc theo dõi quảng cáo thương mại tự động tại thị trường Mỹ qua Graph API chính thức. Đây là lý do bắt buộc phải sử dụng các giải pháp thu thập dữ liệu chuyên dụng như Apify.

---

## 6. NHIỆM VỤ 5 — KẾ HOẠCH THEO DÕI NHỎ NHẤT CÓ CĂN CỨ (THE SMALLEST JUSTIFIED PLAN)

Hệ thống xây dựng phương án kiểm tra T+14 cho 6 quảng cáo cốt lõi với chi phí tối ưu tuyệt đối:

### 1. Cấu hình kỹ thuật:
- **Nhà cung cấp:** Apify (`automation-lab/facebook-ads-library`).
- **Nguồn đầu vào:** 6 Facebook Page ID độc bản:
  `["1294258113779496", "122094798914008278", "1427580890438766", "1254199584442968", "889767694223771", "1238627265989998"]`
- **Bộ lọc:** `country = "US"`, `activeStatus = "all"`, `sortBy = "recent"`, `maxAds = 10` cho mỗi Page.

### 2. So sánh 2 mô hình thực thi:

```
┌──────────────────────────────────────┬───────────────────────────────────┬───────────────────────────────────┐
│ Tiêu chí so sánh                     │ Phương án A: 1 Lượt chạy gộp      │ Phương án B: 6 Lượt chạy cô lập   │
├──────────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────┤
│ Số lượt chạy Actor (Runs)            │ 1 Run duy nhất                    │ 6 Runs tuần tự                    │
│ Phí khởi chạy ($0.0050 / run)        │ $0.0050 USD                       │ $0.0300 USD                       │
│ Số quảng cáo tối đa tính phí         │ 60 quảng cáo (6 pages × 10 ads)   │ 60 quảng cáo                      │
│ Phí trích xuất ad ($0.000575 / ad)   │ $0.0345 USD                       │ $0.0345 USD                       │
│ Tổng chi phí dự toán (Expected Cost) │ $0.0395 USD (~4 xu Mỹ)            │ $0.0645 USD (~6.5 xu Mỹ)          │
│ Hạn mức trần cứng an toàn (Max Cap)  │ $0.0500 USD                       │ $0.0800 USD ($0.0150/task)        │
│ Ưu điểm kỹ thuật                     │ Tiết kiệm tối đa chi phí start fee│ Cô lập rủi ro nếu 1 Page bị lỗi   │
└──────────────────────────────────────┴───────────────────────────────────┴───────────────────────────────────┘
```

> [!TIP]
> **Đề xuất khuyến nghị:** Sử dụng **Phương án B (6 Lượt chạy cô lập tuần tự)**. Dù chi phí cao hơn 2.5 xu Mỹ ($0.0645 so với $0.0395), việc chạy độc lập từng Page giúp bảo vệ quá trình thu thập: Nếu một nhà bán hàng đóng cửa trang Facebook (như Cresomall), lỗi đó sẽ không làm hủy bỏ toàn bộ phiên thu thập của 5 nhà bán hàng còn lại.

---

## 7. TRẢ LỜI ĐẦY ĐỦ 6 CÂU HỎI THEO YÊU CẦU

### 1. Actor đã chọn có thể theo dõi trực tiếp các mã Ad ID hiện có không?
**KHÔNG THỂ.**  
Tài liệu chính thức của `automation-lab/facebook-ads-library` quy định rõ ràng rằng các đường dẫn quảng cáo đơn lẻ (`?id=...`) sẽ bị bỏ qua và xuất hiện cảnh báo (`EXACT_ID_LOOKUP_UNSUPPORTED`). Không có tham số `adArchiveIds` trong schema đầu vào.

### 2. Nếu không, phương thức theo dõi nào có căn cứ bằng chứng được hỗ trợ?
**THEO DÕI THEO FACEBOOK PAGE ID CỦA NHÀ BÁN HÀNG.**  
Actor hỗ trợ cào danh mục quảng cáo đang hoạt động của từng thương hiệu thông qua `pageUrls` hoặc `view_all_page_id`. Hệ thống sẽ cào tối đa 10 quảng cáo gần nhất của từng Page và so khớp mã `adArchiveId` với mã mục tiêu T0.

### 3. Ước tính chi phí thực tế nhỏ nhất là bao nhiêu?
- Nếu chạy gộp 1 lần duy nhất: **$0.0395 USD** (~4 xu Mỹ).
- Nếu chạy 6 tác vụ cô lập an toàn: **$0.0645 USD** (~6.5 xu Mỹ).
- Hạn mức ngân sách trần tối đa cần thiết lập: **$0.0800 USD** (dưới 8 xu Mỹ).

### 4. Giới hạn của việc xác minh trạng thái là gì?
- Nếu quảng cáo mục tiêu xuất hiện: Xác minh được 100% `OBSERVED_ACTIVE` hoặc `OBSERVED_INACTIVE`.
- Nếu quảng cáo mục tiêu vắng mặt: Chỉ được phép ghi nhận là **`UNKNOWN (ABSENT_FROM_WINDOW)`**. Không được coi đây là bằng chứng quảng cáo đã tắt vì có thể quảng cáo bị đẩy xuống dưới do giới hạn phân trang (`maxAds = 10`).

### 5. Ngày đo kiểm đề xuất cho từng nhóm cơ sở (Baseline Cohorts) là ngày nào?
- **Cohort 1 (20 quảng cáo Phase 7):** Đo kiểm T+14 vào ngày **23/11/2026**.
- **Cohort 2 (125 quảng cáo Phase 10):** Đo kiểm T+14 vào ngày **24/11/2026** (theo giờ ICT Việt Nam).

### 6. Có cần thực hiện bất kỳ lượt kiểm tra trả phí nào trước T+14 không?
**HOÀN TOÀN KHÔNG.**  
Hợp đồng dữ liệu và tính khả thi của phương thức tìm kiếm theo Page ID đã được chứng minh qua schema `v0.1` và 2 lượt chạy thực tế (Task 13 & 14) của Phase 10. Mọi khoản chi trước T+14 đều là lãng phí và phá vỡ nguyên tắc quan sát dọc 14 ngày.

---

*Báo cáo tiền kiểm soát được hoàn thành bởi US WIN HUNTER — Intelligence Orchestrator.*  
*Đường dẫn lưu trữ: `docs/T14_MONITORING_PROVIDER_PREFLIGHT.md`*
