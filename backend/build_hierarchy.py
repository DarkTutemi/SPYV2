import json
from collections import defaultdict

with open("backend/data_inventory.json", encoding="utf-8") as f:
    prods = json.load(f)

print(f"Total products in DB: {len(prods)}")

# Define Solution Categories and Consumer Problems
# Hierarchy:
# Consumer Problem -> Solution Category -> Physical Product Type -> Brand/Supplier -> Ad Headlines

# Map known products to physical product types
def classify_product(p):
    ad_body = (p.get("ad_body") or "").lower()
    ad_title = (p.get("ad_title") or "").lower()
    landing = (p.get("landing_page_url") or "").lower()
    name = (p.get("name") or "").lower()
    text = f"{name} {ad_title} {ad_body} {landing}"
    
    # 1. False Positives
    if any(k in text for k in ["novel", "monovellnk", "blinkdrama", "goodnovel", "fixbt", "chapter"]):
        return ("Entertainment & Digital", "Web Novel / Drama App", "Digital Content Subscription", False)
    if "facebook.com/events" in text or "auction" in text:
        return ("Events & Services", "Local Estate Auction", "Auction Event", False)
    if "doordash" in text:
        return ("Local Delivery", "Food/Grocery Delivery App", "Delivery Service", False)
    if "smartcarting.com" in text:
        return ("Automotive Interior", "Car Seat Gap Drop Prevention", "Seat Gap Filler (Affiliate)", False)
    if "getrichdetailing" in text:
        return ("Business & Services", "Detailing Business Coaching / CRM", "Digital Course / SaaS", False)
    if any(k in text for k in ["kavalix", "gastroshield"]):
        return ("Equine Health", "Horse Digestion & Weight", "Equine Feed Powder Supplement", False)
    if any(k in text for k in ["elvora", "black-seed-oil", "bloated"]):
        return ("Human Health & Wellness", "Bloating & Gut Inflammation", "Oregano & Black Seed Oil Drops", False)
    if any(k in text for k in ["receding-gums", "metabolae", "gum", "periodontal"]):
        return ("Oral Care & Health", "Periodontal Gum Recession", "Gum Repair Topical Liquid/Oil", False)
    if any(k in text for k in ["mydermadream", "melasmin", "crepey", "myotide", "eye renewal", "p7 eye", "bloomandbond", "glp-1"]):
        return ("Beauty & Skincare", "Anti-Aging & Skin Tone", "Topical Cosmetic Cream / Drops", False)
    if any(k in text for k in ["palletforks", "skid-steer", "flail mower", "bale spear", "tooth bar", "leveler"]):
        return ("Industrial & Agriculture", "Skid Steer Attachments", "Heavy Steel Tractor Implements", False)

    # 2. Genuine Consumer Physical Products
    # A. Spin Mop Replacement Heads
    if any(k in text for k in ["spin mop", "mop replacement", "mop heads", "mop cloth"]):
        return ("Floor Cleaning & Maintenance", "Spin Mop Head Replacements", "Microfiber Spin Mop Heads", True)
    # B. Dual Magnetic Windshield Cleaner
    if "dual magnetic" in text or "both sides of your windshield" in text:
        return ("Automotive Maintenance", "Windshield Cleaning & Clarity", "Dual Magnetic Glass Cleaner", True)
    # C. Extendable Car Window Wand
    if "windshield cleaning tool" in text or "extendable handle" in text or "car window cleaner kit" in text or "window wand" in text:
        return ("Automotive Maintenance", "Windshield Cleaning & Clarity", "Extendable Handle Glass Cleaning Wand", True)
    # D. Chair Leg Floor Protectors
    if "chair leg" in text or "furniture leg" in text or "leg protector" in text:
        return ("Furniture & Floor Care", "Floor Scratch & Noise Protection", "Silicone Chair Leg Protectors", True)
    # E. Reusable Pet Pee Pads
    if "pee pad" in text or "puppy pad" in text or "pet pad" in text:
        return ("Pet Waste Management", "Dog Indoor Waste Protection", "Washable Multi-Layer Reusable Pee Pads", True)
    # F. Winter Dog Boots / Paw Protectors
    if "dog boot" in text or "paws" in text and ("boot" in text or "cold" in text or "winter" in text or "salt" in text):
        return ("Pet Outdoor Gear", "Dog Winter Paw Protection", "Plush-Lined Waterproof Dog Boots", True)
    # G. Dog Paw Cleaner / Muddy Paws
    if "muddy" in text or "penzh" in text:
        return ("Pet Care & Grooming", "Dirty Dog Paw Cleaning", "Dog Paw Washer / Cleaner", True)
    # H. Damaged Bolt & Screw Extractor
    if "bolt extractor" in text or "screw extractor" in text or "stripped screw" in text or "stripped fastener" in text or "bolt & screw remover" in text or "nut-and-bolt" in text or "hardvoro" in text:
        return ("Tools & Hardware", "Stripped / Damaged Fastener Removal", "High-Speed Steel Bolt & Screw Extractor Set", True)
    # I. Anti-Slip Rug Grippers
    if "rug gripper" in text or "sliding rug" in text or "anti-curling" in text:
        return ("Home Safety & Flooring", "Rug Slipping & Corner Curling", "Rubber Anti-Curling Rug Grippers", True)
    # J. Functional Leakproof Apparel
    if "leak" in text and ("underwear" in text or "boxer" in text) or "menvault" in text or "revol" in text:
        return ("Functional Apparel", "Male Incontinence / Bladder Leaks", "Leakproof Absorbent Boxer Briefs", True)
    # K. Microfiber Car Detailing Towels
    if "detailing towel" in text or "drying towel" in text or "car towel" in text or "synthetic-c" in text:
        return ("Automotive Detailing", "Scratch-Free Vehicle Drying", "Heavy-Duty Microfiber Drying Towels", True)
    # L. Multi-functional Vegetable Peeler
    if "vegetable peeler" in text or "peeler" in text:
        return ("Kitchen Utensils", "Food Prep Efficiency", "Stainless Steel Dual Vegetable Peeler", True)
    # M. Diamond Painting Sealer Spray
    if "diamond" in text and "sealer" in text:
        return ("Crafts & Hobbies", "Diamond Art Preservation", "Diamond Painting Gloss Sealer Spray", True)
    # N. Rechargeable Wide-Beam Headlamp
    if "headlamp" in text or "230° wide" in text:
        return ("Lighting & Outdoor", "Hands-Free Night Illumination", "Rechargeable 230° Wide-Beam Headlamp", True)
    # O. LED Aircraft Strobe Lights
    if "strobe" in text or "aircraft strobe" in text:
        return ("Automotive / Safety Lighting", "Vehicle Anti-Collision Warning", "Rechargeable Wireless Mini Strobe Lights", True)
    # P. LED Note / Message Board
    if "note board" in text or "glow draw" in text:
        return ("Home & Kids Novelty", "Message & Creative Display", "Illuminated Acrylic LED Note Board", True)
    # Q. Astronaut Galaxy Projector
    if "astronaut" in text or "galaxy" in text:
        return ("Home Ambiance", "Room Lighting & Sleep Ambiance", "Astronaut Star Nebula Projector Lamp", True)
    # R. Dog Couch Protection Blanket
    if "couch blanket" in text or "sofa cover" in text or "sfdgwb" in text:
        return ("Furniture Protection", "Pet Furniture Damage Prevention", "Waterproof Dog Furniture Cover Blanket", True)
    # S. Dog Raincoat
    if "raincoat" in text:
        return ("Pet Outdoor Gear", "Dog Wet Weather Walking", "Full-Body 4-Leg Dog Raincoat", True)
    # T. Flat Squeeze Mop
    if "flat mop" in text or "lazy clean" in text:
        return ("Floor Cleaning & Maintenance", "Hands-Free Floor Mopping", "Self-Wringing Hands-Free Flat Mop", True)
    # U. Drill Brush Cleaning Set
    if "drill brush" in text:
        return ("Deep Cleaning Tools", "Power Scrubber Surface Cleaning", "Power Drill Scrubber Brush Attachment Set", True)
    # V. Security Camera / Fidget Stand / Metal Art
    if "security cam" in text:
        return ("Home Security", "Discreet Monitoring", "Mini Wireless HD Security Camera", True)
    if "fidget" in text or "phone stand" in text:
        return ("Phone Accessories", "Hands-Free Phone Viewing & Fidget", "Magnetic 360 Phone Stand & Fidget Spinner", True)
    if "wall art" in text or "cow" in text:
        return ("Home Decor", "Wall Decoration", "Rustic Metal Highland Cow Wall Art", True)
    if "schnauzer" in text or "advent" in text:
        return ("Gifts & Holidays", "Pet Lover Holiday Countdown", "24-Day Dog Lover Advent Calendar", True)
    if any(k in text for k in ["refrigerator", "apal magnetiko", "plaukts"]):
        return ("Kitchen Organization", "Refrigerator Side Storage", "Magnetic Refrigerator Spice Rack", True)
    if "jewelry scratch" in text:
        return ("Jewelry Care", "Jewelry Scratch Removal", "Jewelry Scratch Repair Pen", True)
    if "adult diaper" in text or "alibaba.com" in text:
        return ("Personal Care", "Adult Incontinence Bulk Supply", "Disposable Adult Diapers (B2B / Alibaba)", False)
    if any(k in text for k in ["draft", "door draft", "under door", "cold air"]):
        return ("Household Insulation", "Draft & Air Leak Sealing", "Under-Door Draft Stopper", True)
    if "car care" in text or "maxl" in text:
        return ("Automotive Detailing", "Quick Exterior Detailing", "Ceramic Coating Detailer Spray", True)

    return ("Other / Uncategorized", "General Consumer Need", p["name"][:35], True)

# Group products
hierarchy = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
stats = {
    "total": len(prods),
    "genuine_physical": 0,
    "false_positives": 0,
    "solutions": set(),
    "physical_product_types": set(),
    "brands": set(),
}

categorized_list = []
for p in prods:
    prob, sol, phys, is_phys = classify_product(p)
    if is_phys:
        stats["genuine_physical"] += 1
        stats["solutions"].add(sol)
        stats["physical_product_types"].add(phys)
    else:
        stats["false_positives"] += 1
    
    brand = p["advertiser_name"]
    stats["brands"].add(brand)
    
    hierarchy[prob][sol][phys].append({
        "product_id": p["id"],
        "name": p["name"],
        "brand": brand,
        "landing_url": p["landing_page_url"],
        "is_physical": is_phys,
        "status": p["opportunity_status"],
        "score": p["composite_score"],
    })
    
    categorized_list.append({
        "product_id": p["id"],
        "name": p["name"],
        "problem": prob,
        "solution": sol,
        "physical_type": phys,
        "is_physical": is_phys,
        "brand": brand,
        "score": p["composite_score"],
        "status": p["opportunity_status"]
    })

print(f"\n=== CLASSIFICATION SUMMARY ===")
print(f"Total Products in DB: {stats['total']}")
print(f"Genuine Physical Products: {stats['genuine_physical']}")
print(f"False Positives (Supplements/Digital/Industrial/Affiliate): {stats['false_positives']}")
print(f"Distinct Consumer Solution Types (Physical): {len(stats['solutions'])}")
print(f"Distinct Physical Product Archetypes: {len(stats['physical_product_types'])}")
print(f"Distinct Advertisers/Brands: {len(stats['brands'])}")

print("\n=== DISTINCT CONSUMER SOLUTIONS (PHYSICAL) ===")
for sol in sorted(stats["solutions"]):
    phys_types = [p["physical_type"] for p in categorized_list if p["solution"] == sol]
    brands = set(p["brand"] for p in categorized_list if p["solution"] == sol)
    count = len(phys_types)
    print(f"- {sol} ({count} products across {len(brands)} brands): {list(set(phys_types))}")

with open("backend/product_hierarchy.json", "w", encoding="utf-8") as f:
    json.dump(categorized_list, f, indent=2, ensure_ascii=False)
