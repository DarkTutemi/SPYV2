# BIÊN BẢN QUYẾT ĐỊNH ĐẶC TẢ KỸ THUẬT: DẢI KÍCH CỠ & THÔNG SỐ V4 (SDR-001)
## SPECIFICATION DECISION RECORD: COMMERCIAL SIZING & ENGINEERING TARGETS
### V4 — FULL-SPINE ULTRA OVERNIGHT™ | SPYV2 RESEARCH SUITE

- **Mã văn kiện:** `SDR-001-SIZING-AND-SPEC`
- **Ngày ban hành:** 14 Tháng 11, 2026
- **Trạng thái:** **SPECIFICATION DISCREPANCY RECORDED — PENDING FACTORY CONFIRMATION**
- **Áp dụng cho:** Kế hoạch sản xuất OEM, Cấu hình kênh bán lẻ Shopify, và Tài liệu truyền thông sáng tạo V4.

---

## 1. GHI NHẬN SỰ KHÁC BIỆT ĐẶC TẢ HIỆN TẠI (CURRENT DISCREPANCY RECORD)

Hệ thống ghi nhận sự không nhất quán giữa hai cấu hình kích cỡ đang lưu hành trong dự án SPYV2:

| Tiêu Chí Đối Soát | Đề Xuất Nghiên Cứu SPYV2 (Research / Launch Proposal) | Cấu Hình Shopify & Hồ Sơ Gốc OEM (`PROTOTYPE_V4_FLAGSHIP_SPEC.md`) |
|---|---|---|
| **Dải kích cỡ (Size Range)** | **XS, S, M, L, XL, 2XL, 3XL** | **XS, S, M, L, XL, 2XL, 3XL, 4XL** |
| **Tổng số phân loại SKU (Size Count)** | **7 kích cỡ** | **8 kích cỡ** |
| **Căn cứ đề xuất** | Tối ưu hóa số lượng SKU lưu kho (Inventory SKU rationalization) cho đợt ra mắt đầu tiên; tập trung ngân sách thử nghiệm vào nhóm khách hàng phổ biến nhất (vòng eo 24" – 48"). | Đảm bảo tính bao hàm tối đa cho phân khúc ngoại cỡ (Extended Plus-Size inclusivity theo chuẩn ASTM D5585), đáp ứng phụ nữ sau sinh và cơ địa đùi/mông lớn (vòng eo đến 49.5", vòng mông đến 59.5"). |
| **Tình trạng Shopify (TRYMALORA)** | Chưa cập nhật — giữ nguyên cấu hình hiện hữu. | Hiện diện trên cấu hình phát triển sản phẩm ban đầu. |

---

## 2. NGUYÊN TẮC GIẢI QUYẾT & QUY CHUẨN ĐIỀU HÀNH (GOVERNANCE DIRECTIVE)

1. **Tuyệt đối không tự động chỉnh sửa Shopify (Zero Automated Shopify Mutation):**
   - Không được thực hiện bất kỳ lệnh API hoặc script tự động nào nhằm xóa hay thay đổi biến thể (variants) của cửa hàng Shopify / TRYMALORA khi chưa có phê duyệt bằng văn bản từ Giám đốc Vận hành (COO).
2. **Không tuyên bố phê duyệt từ xưởng may khi chưa có xác nhận rập (No Fabricated Manufacturer Approval):**
   - **Tuyệt đối không được quảng bá hay khẳng định với khách hàng/đối tác rằng dải size XS–3XL hay XS–4XL đã được "nhà sản xuất phê duyệt" (Manufacturer-Approved).**
   - Trạng thái pháp lý của cả hai dải size là: **ĐỀ XUẤT THIẾT KẾ ĐANG CHỜ XÁC NHẬN BẢNG THÔNG SỐ RẬP NHẢY SIZE (PENDING FACTORY GRADED CHART & MOQ CONFIRMATION).**
   - Quyết định chốt 7 size hay 8 size sẽ phụ thuộc vào:
     - Biểu phí làm rập (pattern grading fee) cho size 4XL từ nhà máy OEM.
     - Yêu cầu số lượng đặt hàng tối thiểu (MOQ) trên từng size của nhà máy.
     - Kết quả đo đạc độ co rút và độ ôm đùi của mẫu rập thực tế.
3. **Phân định rõ dải kích cỡ may mẫu thử ban đầu (Initial Factory Prototype Testing Range):**
   - Bất kể quy mô thương phẩm cuối cùng là 7 size hay 8 size, giai đoạn may mẫu thử ban đầu tại xưởng chỉ giới hạn ở **3 kích cỡ:** `S, M, L`.
   - **Size M** là kích cỡ chuẩn (reference size) để đo đạc chiều dài vách lót 46 cm và kiểm định độ vừa vặn trên mannequin nhân trắc học tiêu chuẩn.

---

## 3. TÁI KHẲNG ĐỊNH CÁC MỤC TIÊU KỸ THUẬT CHƯA KIỂM CHỨNG (UNVERIFIED ENGINEERING TARGETS)

Toàn bộ các thông số kỹ thuật cốt lõi dưới đây phải luôn được dán nhãn minh bạch là **MỤC TIÊU THIẾT KẾ KỸ THUẬT (UNVERIFIED ENGINEERING TARGETS)** trong mọi tài liệu kỹ thuật, briefs và kịch bản truyền thông:

1. **Chiều dài vách lót bảo vệ lưng 46 cm (Continuous 46 cm Gusset):**
   - Là mục tiêu thiết kế rập cho size M. Kích thước thực tế có thể thay đổi theo tỷ lệ nhảy size (size grading progression) từ XS đến 3XL/4XL. Bắt buộc đo đạc lại trên mẫu xuất xưởng.
2. **Dung tích thấm hút 150–160 mL (~10–12 Super Tampons):**
   - Là mục tiêu thiết kế lý thuyết của cấu trúc lõi 5 tầng (5-Layer Advanced System). Nghiêm cấm quảng bá như kết quả thực tế cho đến khi có biên bản kiểm nghiệm từ phòng lab độc lập (modified ISO 9073-6 / AATCC 197).
3. **Độ bền màng chống thấm 50–100 chu kỳ giặt (WashGuard):**
   - Là mục tiêu độ bền thiết kế của màng TPU thoáng khí dán ép nhiệt PUR dot. Cần biên bản thử nghiệm giặt lặp lại AATCC 135 xác nhận không bong tách màng.
4. **Bờ cản 3D SideSeal™ ôm khít viền đùi:**
   - Là ý tưởng thiết kế gờ co giãn chống tràn bên mép đùi khi nằm nghiêng. Bắt buộc phải thử nghiệm fitting trên người mẫu thực tế để xác nhận không gây hằn siết hoặc cuộn mép.
