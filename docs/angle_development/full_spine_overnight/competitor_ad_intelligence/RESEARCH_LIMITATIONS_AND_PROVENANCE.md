# GIỚI HẠN NGHIÊN CỨU, NGUỒN GỐC DỮ LIỆU & QUY CHUẨN XÁC THỰC
## METHODOLOGY, EVIDENCE INTEGRITY, RESEARCH LIMITATIONS & SPEND DISCLOSURE

- **Dự án:** SPYV2 / US WIN HUNTER — Competitor Ad Intelligence Suite
- **Sản phẩm đối chứng:** V4 — FULL-SPINE ULTRA OVERNIGHT™
- **Ngày hoàn tất kiểm toán:** 14 Tháng 11, 2026 (Audit Baseline: `cb67b24`)
- **Tình trạng chi phí:** Apify Run: 0 | Chi phí thực hiện: $0.00 (Zero Unauthorized Spend)
- **Trạng thái đóng băng T+14:** Đóng băng 100% đến sau 01:26:00 ICT ngày 24-11-2026.

---

## 1. NGUỒN GỐC DỮ LIỆU & PHƯƠNG PHÁP QUAN SÁT (PROVENANCE & OBSERVATION METHOD)

Bộ dữ liệu gồm 58 bản ghi quảng cáo đối thủ được thu thập và xác thực qua các kênh sau:
1. **Thu thập trực tiếp qua trình duyệt Chrome DevTools (DOM Meta Ad Library Capture):**
   - Thực hiện bởi Subagent phiên bản làm việc `eb8cc491-d172-4a35-9492-5b6b49083086` vào lúc `2026-11-13T22:58:17+07:00`.
   - Đối tượng trích xuất: Thẻ quảng cáo DOM của Meta Ad Library, xác thực tên nhà quảng cáo, trạng thái hoạt động, ngày bắt đầu chạy, văn bản copy đầy đủ, liên kết đích và phần tử `<video>` / `<img>` cùng poster thumbnail.
2. **Xác thực kho lưu trữ công khai & trang bán hàng DTC (Public Library & DTC Archive):**
   - Xác thực sự tồn tại của sản phẩm và chiến dịch đang chạy trên website chính hãng của các thương hiệu (Knix, Revol Cares, Saalt, Thinx, The Period Company).
3. **Chiến dịch lưu trữ lịch sử ngành (Historical Case Study):**
   - Chiến dịch Thinx 2019 "MENstruation" được dẫn chiếu từ tài liệu nghiên cứu truyền thông và báo chí uy tín.

---

## 2. KẾT QUẢ TÁI KIỂM TOÁN TẦNG BẰNG CHỨNG (RE-AUDIT OF EVIDENCE TIERS)

Quy chuẩn kiểm toán thương mại độc lập của `SPYV2` đặt ra nguyên tắc: **Văn bản copy quảng cáo và siêu dữ liệu thời lượng video (video duration metadata) tuyệt đối không được coi là bằng chứng đã xem video thực tế.**

Dựa trên nguyên tắc này, toàn bộ 12 bản ghi trước đây được gắn nhãn tạm thời `VERIFIED_VIDEO` đã được tái kiểm toán và phân loại lại minh bạch:
- **10 bản ghi trích xuất từ DOM Meta Ad Library:** Được hạ cấp chính xác xuống **`VERIFIED_AD_CARD`** (Mức độ tin cậy: **85/100**). Thẻ quảng cáo, văn bản copy và thẻ video trong DOM được bảo chứng, nhưng chưa thực hiện xem playback từng khung hình hoặc bóc băng ghi âm lời thoại.
- **2 bản ghi từ kho lưu trữ DTC/Public Library (Thinx và Revol Cares):** Được hạ cấp xuống **`VERIFIED_AD_LIBRARY_ACTIVE`** (Mức độ tin cậy: **90/100**).
- **Hiện tại không có bản ghi nào giữ nhãn `VERIFIED_VIDEO` (0 / 58)**, loại bỏ triệt để nguy cơ phóng đại mức độ xác thực.

### Bảng phân bố tầng bằng chứng sau kiểm toán (N = 58)

| Tầng Bằng Chứng (`evidence_status`) | Số lượng | Tỷ lệ (%) | Mức tin cậy | Tiêu chuẩn Đạt chuẩn |
|---|---|---|---|---|
| `VERIFIED_AD_CARD` | **51** | **87.9%** | **85 / 100** | Thẻ quảng cáo, copy và cấu trúc phần tử DOM được xác thực qua DevTools. |
| `VERIFIED_AD_LIBRARY_ACTIVE` | **6** | **10.3%** | **90 / 100** | Thẻ quảng cáo công khai trên Meta Ad Library và trang sản phẩm DTC hoạt động. |
| `HISTORICAL_SOURCE` | **1** | **1.7%** | **90 / 100** | Chiến dịch lịch sử có tài liệu lưu trữ ngành chứng thực. |
| `VERIFIED_VIDEO` | **0** | **0.0%** | **95 / 100** | Tạm thời bằng 0 (chờ quy trình ghi hình playback độc lập). |
| `UNVERIFIED` | **0** | **0.0%** | **0 / 100** | Không có quảng cáo ngụy tạo hoặc thiếu nguồn gốc. |
| **Tổng cộng** | **58** | **100.0%** | **85.7 (TB)** | **100% bản ghi được bảo chứng nguồn gốc thực tế.** |

---

## 3. TÁCH BIỆT MẪU ĐỐI THỦ CỐT LÕI & TIÊU CHUẨN NGÀNH

Để tránh làm sai lệch số liệu tần suất góc tiếp cận, báo cáo đã phân tách rành mạch:
- **Nhóm Top 5 Đối thủ Trực tiếp (N = 45):** Knix (33), Saalt (4), Thinx (4), The Period Company (2), Revol Cares (2).
- **Nhóm Tiêu chuẩn Ngành (N = 13):** Lil Helper (3), Hello Period (2), Veloura (2), Always ZZZ (1), Organyc (1), Peace Pads (1), Dailys (1), Rejuveen (1), Orykas (1).

---

## 4. CÁC HIỆU CHỈNH KHOA HỌC & GIỚI HẠN NGHIÊN CỨU CẦN LƯU Ý

1. **Loại bỏ khẳng định chưa kiểm chứng về 80% rò rỉ lưng:**
   - Đã xóa bỏ hoàn toàn nhận định cho rằng "80% rò rỉ ban đêm xảy ra ở lưng". Thay vào đó, phân tích hiện tượng này dựa trên quy luật trọng lực tự nhiên khi nằm ngửa làm dịch kinh dồn về phía rãnh lưng.
2. **Thay thế thuật ngữ "Massive Whitespace":**
   - Đã thay thế bằng cụm từ chính xác về mặt thống kê: **"Góc tiếp cận ít xuất hiện trong tập mẫu quan sát (Underrepresented in the observed sample)"**, phản ánh đúng việc chỉ có 2/45 quảng cáo đối thủ (4.4%) đề cập đến vách lót mở rộng ra sau lưng.
3. **Phân biệt hai dòng sản phẩm riêng biệt của Revol Cares:**
   - **The Charlie:** Dòng quần boxer siêu thấm với dung tích công bố lên đến **140 mL** và vách lót waistband-to-waistband.
   - **The Sleep Short:** Dòng quần ngủ riêng biệt với dung tích công bố **70 mL**.
4. **Phân định giữa giả thuyết phân tích và bằng chứng thực tế:**
   - Các điểm hạn chế về kỹ thuật của đối thủ (ví dụ: đường may dán ép phẳng của Knix dễ bị tràn mép đùi khi nằm nghiêng, hoặc vải cotton fleece của Period Co giữ ẩm lâu) được phân loại là **giả thuyết phân tích kỹ thuật (Analyst Engineering Hypotheses)** hoặc **phản hồi trải nghiệm người dùng chưa chuẩn hóa (Anecdotal Consumer Reports)**, không phải kết quả thử nghiệm độc lập trên từng mã SKU.
5. **Thời gian hiển thị quảng cáo không đồng nghĩa với chỉ số chuyển đổi nội bộ:**
   - Dữ liệu Meta Ad Library phản ánh sự tồn tại và thời gian chạy của quảng cáo. Thời gian chạy dài là một chỉ báo hợp lý cho thấy quảng cáo mang lại hiệu quả chi phí, nhưng không thay thế cho các chỉ số nội bộ (CTR, ROAS, CPA, Conversion Rate).
