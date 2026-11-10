import json

with open("backend/promising_audit_results.json", encoding="utf-8") as f:
    items = json.load(f)

surviving = [x for x in items if x["classification"] in ("HIGH_CONFIDENCE_PROMISING", "PLAUSIBLE_BUT_UNVERIFIED")]

classified = []
class_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}

for item in surviving:
    name = item["name"].lower()
    url = (item["landing_url"] or "").lower()
    reason = item.get("reason", "").lower()
    text = f"{name} {url} {reason}"

    # Class B: Multiple pieces required to cover one household or complete one functional set
    if any(k in text for k in ["chair leg", "protector", "rug", "curling", "boot"]):
        cls = "B"
        cls_name = "B. Che phủ đồ gia dụng hoặc hoàn thành 1 set chức năng (Multiple pieces per set/house)"
        explanation = "1 bàn ăn cần 16-32 nút bọc (4-8 ghế x 4 chân); 1 tấm thảm cần 4 miếng góc; 1 chú cún cần đúng 4 chiếc ủng (1 set)."
    # Class C: Complete tool kit containing multiple components
    elif any(k in text for k in ["bolt", "extractor", "fastener", "screw", "hardvoro"]):
        cls = "C"
        cls_name = "C. Bộ dụng cụ hoàn chỉnh chứa nhiều chi tiết (Complete tool kit with multiple components)"
        explanation = "Bộ mũi nhổ 5-10 chi tiết là MỘT bộ dụng cụ duy nhất cho nhiều cỡ ốc; khách hàng mua 1 bộ, không có nhu cầu mua 5-10 bộ."
    # Class A: Multiple complete units needed for regular use
    elif any(k in text for k in ["pee pad", "puppy pad", "mop", "leak", "boxer", "underwear"]):
        cls = "A"
        cls_name = "A. Cần nhiều đơn vị hoàn chỉnh để sử dụng định kỳ (Multiple complete units for regular use)"
        explanation = "Xoay vòng giặt ủi hàng ngày (thảm tè, boxer) hoặc tiêu hao định kỳ (đầu lau xoay 360°)."
    # Class D: Artificial discount bundles
    elif any(k in text for k in ["windshield", "headlamp", "sealer", "peeler"]):
        cls = "D"
        cls_name = "D. Combo chiết khấu nhân tạo (Artificial discount bundles)"
        explanation = "1 dụng cụ có thể dùng cho nhiều xe/vật thể; việc mua 2-3 cái chủ yếu do nhà bán hàng kích cầu giảm giá hoặc mua tặng."
    else:
        cls = "E"
        cls_name = "E. Chưa đủ bằng chứng (Insufficient evidence)"
        explanation = "Chưa có đủ dữ liệu hành vi người dùng về tần suất mua lại hoặc mua nhiều đơn vị."

    class_counts[cls] += 1
    classified.append({
        "id": item["id"],
        "name": item["name"],
        "brand": item["advertiser"],
        "bundle_class": cls,
        "bundle_class_name": cls_name,
        "explanation": explanation,
        "landing_url": item["landing_url"],
        "score": item["score"]
    })

print("=== BUNDLE NECESSITY CLASSIFICATION FOR 25 SURVIVING CANDIDATES ===")
for k, v in class_counts.items():
    print(f"- Class {k}: {v} candidates ({v/len(surviving)*100:.1f}%)")

with open("backend/bundle_necessity_classification.json", "w", encoding="utf-8") as f:
    json.dump(classified, f, indent=2, ensure_ascii=False)

