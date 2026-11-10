# BÁO CÁO ĐÓNG BĂNG CẤU HÌNH GIÁM SÁT T+14 — US WIN HUNTER
**US WIN HUNTER — FINAL T+14 CONFIGURATION FREEZE & SAFEGUARDS AUDIT**

- **Hệ thống:** US WIN HUNTER — Intelligence Orchestrator
- **Tình trạng:** **ĐÓNG BĂNG HOÀN TOÀN (CONFIGURATION FROZEN)**
- **Khóa an toàn:** `APIFY_AUTO_COLLECTION_ENABLED=false` duy trì nghiêm ngặt.
- **Thời điểm mở lệnh sớm nhất:** **Sau 01:26:00 ngày 24/11/2026 (Giờ ICT / UTC+7, Giờ Việt Nam)**.

---

## 1. GIẢI TRÌNH SỰ KHÁC BIỆT MÃ QUẢNG CÁO MIẾNG DÁN THẢM (RUG GRIPPERS AD ID)

Cơ sở dữ liệu gốc `data/winhunter.db` đối soát toàn diện giữa hai mã quảng cáo:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ĐỐI SOÁT CHI TIẾT HAI BẢN GHI TRONG CƠ SỞ DỮ LIỆU:                                                             │
├──────────────────────────┬───────────────────────────────────────────┬─────────────────────────────────────────┤
│ Tiêu chí                 │ Mã Ad ID: 1691452315890995                │ Mã Ad ID: 1102527249449007              │
├──────────────────────────┼───────────────────────────────────────────┼─────────────────────────────────────────┤
│ Sản phẩm thực tế         │ Giày đi tuyết lót lông cho cún (Dog Boots)│ Miếng dán chống quăn mép thảm (Grippers)│
│ Tiêu đề quảng cáo        │ (Không tiêu đề)                           │ "No More Sliding Rugs!"                 │
│ Thương hiệu              │ Relaxrich                                 │ Gridsparkl/er                           │
│ Facebook Page ID         │ 179087411956645                           │ 1238627265989998                        │
│ Tên miền trang đích      │ relaxrich.com                             │ gridsparkl.com                          │
│ Đường dẫn sản phẩm       │ /products/warm-winter-dog-boots-...       │ /products/rubber-anti-curling-non-slip..│
│ Lượt cào nguồn (Run ID)  │ 0d84f608... (Phase 10, Task 4: dog paws)  │ daf932f4... (Phase 10, Task 14: Gridsp.)│
│ Mốc quan sát T0 (UTC)    │ 2026-11-09 18:23:44                       │ 2026-11-09 18:25:53                     │
│ Bản ghi trong DB         │ ĐÃ LƯU TRỮ VÀ BẢO TOÀN (100%)             │ ĐÃ LƯU TRỮ VÀ BẢO TOÀN (100%)           │
└──────────────────────────┴───────────────────────────────────────────┴─────────────────────────────────────────┤
│ KẾT LUẬN VÀ PHÂN ĐỊNH:                                                                                         │
│ • Mã 1691452315890995 xuất hiện trong tài liệu Phase 13 là do lỗi sao chép nhầm mã văn bản.                   │
│ • Mã 1102527249449007 là mã mục tiêu thật của sản phẩm Miếng dán thảm Gridsparkl.                             │
│ • Cả hai bản ghi đều là dữ liệu thật và được bảo lưu nguyên vẹn; không có việc tráo đổi dữ liệu ngầm.          │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. XÁC NHẬN CÁC RÀNG BUỘC BẢO VỆ NGÂN SÁCH (SPENDING SAFEGUARDS)

1. **Cấu hình trần chi phí $0.08 USD:**
   - Phí khởi tạo `start`: $0.0050 USD.
   - Phí cào tối đa 120 quảng cáo: $120 \times \$0.000575 = \$0.0690 USD.
   - Tổng chi phí kịch bản tối đa: $\$0.0050 + \$0.0690 = \mathbf{\$0.0740\text{ USD}} \le \mathbf{\$0.0800\text{ USD}}$.
2. **Hỗ trợ của nền tảng Apify:** Tham số `maxTotalChargeUsd: 0.08` được truyền trực tiếp khi gọi API tạo Run; nền tảng Apify sẽ tự động cưỡng bức ngắt tiến trình nếu chi phí chạm trần.
3. **Cơ chế khóa an toàn nội bộ (Fail Closed):** Module `reserve_budget()` thực hiện cam kết ngân sách trong bảng `collection_runs` trước khi phát lệnh ra bên ngoài. Nếu hạn mức ngày ($2.00) hoặc tháng ($10.00) bị vượt, hệ thống tự động chặn đứng tác vụ.
4. **Không phát sinh chi phí ẩn:** Mô hình Pay-Per-Event đã bao gồm toàn bộ tài nguyên tính toán (RAM/CPU), không có phụ phí compute-units riêng.

---

## 3. BẢO TOÀN PHẠM VI GIÁM SÁT (PRESERVE MONITORING SCOPE)

- **Đối tượng theo dõi:** Đúng 6 quảng cáo cốt lõi của Watchlist, không quét toàn bộ 145 quảng cáo đường cơ sở.
- **Báo cáo phân tách rành mạch khi có kết quả:**
  - Số quảng cáo mục tiêu được kiểm tra: đúng 6 quảng cáo.
  - Số quảng cáo mục tiêu xác nhận `OBSERVED_ACTIVE`.
  - Số quảng cáo mục tiêu xác nhận `OBSERVED_INACTIVE`.
  - Số quảng cáo mục tiêu vắng mặt trong cửa sổ trích xuất (`UNKNOWN`).
  - Lỗi truy xuất theo từng Page (nếu có).
  - Các quảng cáo mới phát hiện thêm từ các Page này.
- **Nguyên tắc bất biến:** Không coi quảng cáo vắng mặt là đã tắt; không suy diễn chi phí quảng cáo, doanh thu hay lợi nhuận từ việc quảng cáo còn hoạt động.

---

## 4. QUY TRÌNH PHÊ DUYỆT CỦA OPERATOR NGÀY 24/11/2026

- **Điều kiện thời gian bắt buộc:** Sau **01:26:00 ngày 24/11/2026** (Giờ Việt Nam / ICT).
- **Lệnh cần Operator phê duyệt bằng văn bản:**
  > *"Tôi phê duyệt thực hiện duy nhất 1 lượt cào giám sát T+14 qua Actor automation-lab/facebook-ads-library với danh sách 6 Facebook Page ID đã định sẵn, activeStatus='all', maxAds=20/page, tổng chi phí tối đa không vượt quá $0.08 USD."*
- **Tuyệt đối không coi phê duyệt cấu hình hôm nay là lệnh được phép tiêu tiền.** Mọi tiến trình thu thập có phí đều bị đóng băng cho đến khi có lệnh phê duyệt mới vào ngày 24/11.

