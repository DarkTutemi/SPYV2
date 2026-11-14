# RESEARCH LIMITATIONS, PROVENANCE & COMMERCIAL INTEGRITY
## OPERATIONAL METHODOLOGY, AUDITED EVIDENCE TIERING & ZERO-SPEND AUDIT TRAIL
### SPYV2 / US WIN HUNTER — ULTRA OVERNIGHT V4 RESEARCH SUITE (AUDITED)

- **Workspace:** `SPYV2 / US WIN HUNTER` (`https://github.com/DarkTutemi/SPYV2`)
- **Active Git Branch:** `research/ultra-v4-top5-ad-intelligence`
- **Reference Date:** November 14, 2026 (Audited & Qualified)
- **Safety Status:** `APIFY_AUTO_COLLECTION_ENABLED=false`, Spend = $0.00, T+14 Watchlist Frozen

---

## 1. NGUYÊN TẮC LIÊM CHÍNH THƯƠNG MẠI & BẢO TỒN DỮ LIỆU

1. **Bảo tồn Dữ liệu Nguyên bản (Raw Data Preservation):**
   - Tệp dữ liệu ban đầu gồm 58 bản ghi được bảo tồn nguyên vẹn tại: `TOP5_CREATIVE_EVIDENCE_RAW.csv`.
   - Tệp dữ liệu đã qua kiểm toán độc lập được lưu trữ riêng tại: `TOP5_CREATIVE_EVIDENCE_AUDITED.csv` và đồng bộ vào `TOP5_CREATIVE_EVIDENCE.csv`.
2. **Quy tắc Chi phí 0 Đồng (Zero-Spend Operating Rule):**
   - Không kích hoạt bất kỳ tác vụ thu thập trả phí nào qua Apify (`APIFY_AUTO_COLLECTION_ENABLED = false`).
   - Tổng chi tiêu phát sinh: **$0.00 USD**.
3. **Đóng băng Tuyệt đối Thí nghiệm T+14:**
   - Bảo toàn 100% dữ liệu 145 Meta ads, 435 snapshots trong `data/winhunter.db`. Đóng băng cho đến sau 01:26:00 ICT ngày 24-11-2026.
4. **Không Ngụy Tạo Bằng Chứng Video:**
   - Đối với các quảng cáo video trong DOM chưa được trực tiếp mở xem chuyển động hình ảnh và âm thanh, nội dung hook 0–3s được ghi nhận trung thực là: `UNKNOWN (Ad Copy Opening: "...")` và `hook_visual` được ghi là `UNKNOWN (Video Playback Not Inspected)`.

---

## 2. PHÂN CẤP BẰNG CHỨNG ĐÃ KIỂM TOÁN (AUDITED EVIDENCE TIERING)

Toàn bộ 58 bản ghi được phân loại chính xác theo 4 cấp bậc tin cậy:

```
+----------------------------------------------------------------------------------------------------+
| PHÂN CẤP BẰNG CHỨNG            | ĐỊNH NGHĨA KỸ THUẬT                        | ĐỘ TIN CẬY | SỐ LƯỢNG|
+----------------------------------------------------------------------------------------------------+
| **VERIFIED_VIDEO**             | Video quảng cáo được trực tiếp quan sát   | 95         | 12 ad   |
|                                | phát thực tế với bằng chứng hình ảnh/thoại |            | (20.7%) |
+----------------------------------------------------------------------------------------------------+
| **VERIFIED_AD_CARD**           | Thẻ quảng cáo và văn bản copy được trích   | 85         | 41 ad   |
|                                | xuất trực tiếp từ DOM Meta Ad Library     |            | (70.7%) |
+----------------------------------------------------------------------------------------------------+
| **VERIFIED_AD_LIBRARY_ACTIVE** | Quảng cáo đang hoạt động được xác minh qua | 90         |  4 ad   |
|                                | liên kết Ad Library và trang đích DTC     |            | ( 6.9%) |
+----------------------------------------------------------------------------------------------------+
| **HISTORICAL_SOURCE**          | Chiến dịch quảng cáo lịch sử có hồ sơ lưu  | 90         |  1 ad   |
|                                | trữ truyền thông xác thực (Thinx MENstruation) |         | ( 1.7%) |
+----------------------------------------------------------------------------------------------------+
| **TỔNG CỘNG**                  | Đã kiểm toán độc lập, không ngụy tạo       | —          | **58**  |
+----------------------------------------------------------------------------------------------------+
```

### Phương pháp tính điểm tin cậy (Reproducible Confidence Scoring Method):
- `VERIFIED_VIDEO` (95 điểm): Đầy đủ dữ liệu thẻ DOM + URL đích + quan sát thực tế chuyển động và lời thoại video.
- `VERIFIED_AD_CARD` (85 điểm): Dữ liệu thẻ DOM + văn bản copy + nút CTA + URL đích xác thực; video chưa được trực tiếp xem phát.
- `VERIFIED_AD_LIBRARY_ACTIVE` (90 điểm): Liên kết thư viện quảng cáo hoạt động + trang đích DTC xác thực.
- `HISTORICAL_SOURCE` (90 điểm): Dữ liệu chiến dịch lịch sử được ghi nhận trên các tạp chí chuyên ngành uy tín (FastCompany, iSpot).
- *Lưu ý quan trọng:* Điểm số tin cậy đo lường **mức độ đầy đủ và xác thực của bằng chứng quan sát**, hoàn toàn **KHÔNG** đo lường tỷ lệ nhấp (CTR), tỷ lệ chuyển đổi hay tỷ suất lợi nhuận (ROAS) của quảng cáo.

---

## 3. CÁC ĐIỂM HẠN CHẾ & GIẢI TỎA SUY ĐOÁN KINH DOANH

1. **Tuyệt đối không suy diễn hiệu quả tài chính từ thời gian chạy quảng cáo:**
   - Việc một quảng cáo chạy dài hạn (như của The Period Company từ tháng 12/2025) chỉ chứng minh rằng chiến dịch đó **đang duy trì trạng thái hoạt động trên nền tảng Meta**, không phản ánh lợi nhuận ròng, CTR hay ROAS cụ thể.
2. **Kích thước mẫu khảo sát (N = 58):**
   - Phản ánh tập mẫu quảng cáo thực tế thu thập được trong khung thời gian tháng 8 đến tháng 11 năm 2026, không đại diện cho tổng thị phần chi tiêu quảng cáo (Ad Spend Share) của toàn ngành hàng tại Mỹ.
3. **Phân biệt rõ mục tiêu thiết kế và kết quả kiểm định:**
   - Các thông số của V4 (150–160 mL, 46 cm gusset, SideSeal™) là **Mục tiêu kỹ thuật đặt hàng nhà máy (Engineering Targets for RFQ)**, bắt buộc phải có biên bản kiểm nghiệm lab vật lý trước khi công bố như kết quả đã chứng minh.
