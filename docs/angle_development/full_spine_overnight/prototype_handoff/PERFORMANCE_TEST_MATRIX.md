# STANDARDIZED PERFORMANCE VALIDATION MATRIX & BENCH PROTOCOL
## REPRODUCIBLE TESTING PROCEDURES FOR OEM PROTOTYPE EVALUATION

- **Document ID:** `MATRIX-TEST-PROTO-005`
- **Product Title:** Full-Spine 360° Overnight Sleep Shorts
- **Market:** United States (US Only)
- **Status:** ACTIVE LABORATORY BENCH PROTOCOL (Prototype Stage-Gate)
- **Scientific Integrity Mandate:** All procedures defined herein represent executable laboratory protocols. **No passing test results are fabricated or presumed.** All prototypes (V1, V2, V3) must be subjected to actual physical testing, and empirical observations must be recorded honestly.

---

## 1. COMPREHENSIVE PERFORMANCE TESTING MATRIX OVERVIEW

```
+----------------------------------------------------------------------------------------------------+
| # | TEST CATEGORY               | STANDARD APPLICABLE        | PRIMARY METRIC      | BENCHMARK PASS |
+----------------------------------------------------------------------------------------------------+
| 1 | Rapid Fluid Acquisition     | EDANA WSP 070.3.R3 (Mod.)  | Strike-through time | < 2.0 seconds  |
| 2 | Total Absorption Capacity   | ISO 9073-6 / AATCC 79 Mod. | Total retained fluid| ≥ 60–75 mL     |
| 3 | Rear Waistband Incline Leak | Internal 30° Incline Assay | Escaped runoff volume| 0.0 mL escape |
| 4 | Leg Opening Cuff Seal       | Mannequin Lateral Incline  | Inner-thigh run-off | Zero staining  |
| 5 | Compression Rewet Resistance| EDANA WSP 080.4.R3 (Mod.)  | Moisture to blotter | ≤ 0.50 grams   |
| 6 | Dynamic Movement & Fit      | ASTM D3107 / Wear Protocol | Slippage & recovery | < 1.0 cm slip  |
| 7 | Moisture Vapor Transmission | ASTM E96 (Inverted Cup BW) | Vapor loss per 24h  | ≥ 3,000 g/m²/24|
| 8 | Wash Durability (Separated) | AATCC 135 / 127 / ISO 9073 | Dimensional / Hydro | <3% chg; ≥8k mm|
| 9 | Textile Chemical Safety     | ISO 20999 / CA AB 2515     | Total Fluorine / TOF| Non-detect TF  |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. DETAILED TEST PROTOCOLS & FAILURE HANDLING

---

### PROTOCOL 1: RAPID FLUID ACQUISITION TIME (STRIKE-THROUGH SPEED)

- **Governing Standard:** EDANA WSP 070.3.R3 (Adapted for Knitted Hygiene Composites).
- **Equipment & Apparatus:**
  1. Automated liquid strike-through plate with electronic timer sensors.
  2. Graduated dispensing burette calibrated to deliver 10.0 mL fluid at a standardized flow rate ($10\text{ mL / 1.5 s}$).
  3. Test liquid: 0.9% physiological saline solution dyed with 0.1% acid blue dye (surface tension: $70\pm 2\text{ mN/m}$).
- **Specimen Preparation:**
  - Cut $100\times 100\text{ mm}$ specimen from the central perineal zone of the gusset (including all plies).
  - Condition specimen at $21\pm 1^\circ\text{C}$ and $65\pm 2\%$ relative humidity for 24 hours.
- **Step-by-Step Procedure:**
  1. Place the test specimen onto the baseplate with Layer 1 (organic cotton mesh) facing upward.
  2. Lower the electronic strike-through plate onto the specimen surface.
  3. Position the burette tip 10 mm above the strike-through cavity.
  4. Release an initial dose of 10.0 mL saline. The timer starts automatically upon fluid contact and stops when the liquid has completely penetrated below the topsheet.
  5. Record initial strike-through time ($T_1$).
  6. Wait 60 seconds; deliver a second 10.0 mL dose and record second strike-through time ($T_2$).
- **Acceptance Criteria:**
  - **Variant V1:** $T_1 < 2.5\text{ seconds}$; $T_2 < 5.0\text{ seconds}$.
  - **Variant V2:** $T_1 < 1.5\text{ seconds}$; $T_2 < 3.5\text{ seconds}$.
  - **Variant V3 (Hero Target):** $T_1 < 2.0\text{ seconds}$; $T_2 < 4.0\text{ seconds}$.
- **Failure Handling Protocol:**
  - *If $T_1 \ge 2.5\text{ s}$:* Indicates surface hydrophobicity or closed pore structure in organic cotton topsheet. Action: Mandate mill apply a wash-durable hydrophilic bio-finish to topsheet or increase birdseye aperture gauge.

---

### PROTOCOL 2: TOTAL ATMOSPHERIC ABSORPTION CAPACITY (RAW MATERIAL & COMPOSITE BENCHMARK)

- **Governing Standard:** ISO 9073-6:2025 / AATCC 79 Mod. (Method for Absorption of Nonwoven/Textile Composites).
- **Scope & Methodological Distinction:**
  * ISO 9073-6:2025 is an analytical material-level absorption method measuring raw absorbent core nonwoven fabric fluid uptake and retention under free atmospheric immersion.
  * **Critical Distinction:** Material-level absorption capacity does **not** evaluate finished garment leakage, anatomical fit, body compression rewetting (Protocol 5), or perimeter barrier integrity at the waistband and leg openings (Protocols 3 & 4). Garment leak-proofing requires passing all six mechanical bench protocols collectively.
- **Equipment & Apparatus:**
  1. Analytical balance sensitive to 0.01 grams.
  2. Stainless steel immersion basket and horizontal drain rack calibrated to a 30-degree tilt.
  3. Temperature-controlled immersion tank containing 0.9% saline solution at $23\pm 1^\circ\text{C}$.
- **Specimen Preparation:**
  - Full finished prototype garment (Size M), weighed in dry conditioned state ($W_{\text{dry}}$).
- **Step-by-Step Procedure:**
  1. Submerge the full absorbent gusset zone into the saline tank for 20 minutes to achieve complete atmospheric saturation.
  2. Lift the specimen using the horizontal drain rack and allow to drip freely at a 30-degree incline for 2.0 minutes.
  3. Immediately weigh the wet garment on the analytical balance and record wet weight ($W_{\text{wet}}$).
  4. Calculate total fluid capacity: $\text{Capacity (mL)} = \frac{W_{\text{wet}} - W_{\text{dry}}}{1.005\text{ g/mL}}$.
- **Acceptance Criteria:**
  - **Variant V1:** $\ge 80.0\text{ mL}$ total retention.
  - **Variant V2:** $\ge 60.0\text{ mL}$ total retention.
  - **Variant V3 (Hero Target):** $\ge 65.0\text{ mL}$ total retention (equivalent to 6.5 regular tampons).
- **Failure Handling Protocol:**
  - *If Capacity $< 60.0\text{ mL}$:* Indicates insufficient fiber mass or poor microfiber yarn packing. Action: Increase microfiber terry loop weight from 280 GSM to 300 GSM or substitute 80/20 poly/polyamide for 100% polyester.

---

### PROTOCOL 3: REAR WAISTBAND INCLINE LEAKAGE (DYNAMIC SUPINE TEST)

- **Governing Standard:** Internal SPYV2 Mechanical Incline Benchmark (Supine Sleep Simulation).
- **Equipment & Apparatus:**
  1. Anatomical female half-mannequin (US Size M pelvic profile) mounted on a 30-degree incline rig with buttocks elevated and head lowered.
  2. Peristaltic dosing pump with silicone delivery tube positioned at the center crotch point.
  3. White absorbent blotting paper placed beneath the rear waistband edge to capture any escaped runoff.
- **Specimen Preparation:**
  - Mount dry prototype garment onto the inclined mannequin, ensuring waistband sits 1.5" above navel line.
- **Step-by-Step Procedure:**
  1. Dose 25.0 mL of blue-dyed saline at a rapid continuous flow rate of $5.0\text{ mL / second}$ directly onto the crotch area.
  2. Observe fluid flow dynamics via high-speed video: liquid will channel backward along the intergluteal cleft toward the waistband under gravity.
  3. Inspect the rear waistband blotting paper after 60 seconds.
- **Acceptance Criteria:**
  - **Zero Fluid Escape (0.0 mL):** The blotting paper must show **0.0 mm dye staining** beyond the waistband casing.
  - All 25.0 mL fluid must be completely captured within the continuous gusset before reaching the top elastic edge.
- **Failure Handling Protocol:**
  - *If Staining Detected:* Indicates fluid bypassed the stepped-down taper or ran off the sides of the rear flare. Action: Increase rear flare width by +1.0 cm or increase ADL density at the lumbar junction.

---

### PROTOCOL 4: INNER-THIGH LEG OPENING LEAKAGE (LATERAL SLEEP TEST)

- **Governing Standard:** Internal SPYV2 Lateral Incline Benchmark (Side-Sleeping Simulation).
- **Equipment & Apparatus:**
  1. Articulated female mannequin placed in fetal side-sleeping posture (knees flexed at 60 degrees).
  2. Fluid delivery tube directed at the lateral edge of the perineal gusset.
  3. Continuous collection tray underneath the inner-thigh cuff.
- **Step-by-Step Procedure:**
  1. Dose 20.0 mL dyed saline at $2.0\text{ mL / second}$ directly against the inner-thigh leg binding edge while in lateral position.
  2. Monitor for liquid strikethrough across needle holes or fluid rolling around the elastic binding.
- **Acceptance Criteria:**
  - Zero liquid dripping into the collection tray ($0.0\text{ mL}$).
  - Mobilon elastic binding must maintain continuous skin contact without gap formation.
- **Failure Handling Protocol:**
  - *If Lateral Leakage Occurs:* Indicates inadequate crotch width or elastic tension too loose. Action: Increase perineal width from 12.0 cm to 12.5 cm or increase mobilon elastic pre-tension by 15%.

---

### PROTOCOL 5: COMPRESSION REWET RESISTANCE UNDER PRESSURE

- **Governing Standard:** EDANA WSP 080.4.R3 (Rewet Under Load Adapted for Reusables).
- **Equipment & Apparatus:**
  1. Calibrated 5.0 lb (2.27 kg) circular brass weight with 100 mm diameter flat contact base ($0.50\text{ psi}$ static load, simulating adult female sitting or lying pressure).
  2. Pre-weighed Whatman No. 1 laboratory filter paper circles ($100\text{ mm}$ diameter, conditioned at $65\%$ RH).
- **Step-by-Step Procedure:**
  1. Deliver 40.0 mL saline to the central gusset and wait 10 minutes for full capillary distribution.
  2. Place a stack of 10 pre-weighed dry filter papers ($W_{\text{filter\_dry}}$) directly over the central wet zone.
  3. Gently lower the 5.0 lb weight onto the filter papers.
  4. Maintain 0.50 psi static load for exactly 120 seconds.
  5. Remove weight; immediately weigh filter paper stack ($W_{\text{filter\_wet}}$).
  6. Calculate rewet mass: $\Delta W = W_{\text{filter\_wet}} - W_{\text{filter\_dry}}$.
- **Acceptance Criteria:**
  - **Variant V1:** $\Delta W \le 0.65\text{ grams}$.
  - **Variant V2:** $\Delta W \le 0.40\text{ grams}$.
  - **Variant V3 (Hero Target):** $\Delta W \le 0.50\text{ grams}$.
- **Failure Handling Protocol:**
  - *If $\Delta W > 0.50\text{ g}$:* Indicates fluid released from retention core under body weight. Action: Increase microfiber polyamide ratio (from 20% to 25%) or adjust topsheet aperture gauge to increase capillary back-flow resistance.

---

### PROTOCOL 6: COMFORT, RECOVERY & FIT DURING MOVEMENT

- **Governing Standard:** ASTM D3107 (Stretch and Recovery of Knitted Fabrics) + Wear Movement Simulation.
- **Equipment & Apparatus:**
  1. Mechanical constant-rate extension stretcher.
  2. US Size M, 2XL, and 4XL fit mannequins with motorized hip/thigh rotation rig (1,000 cycles).
- **Step-by-Step Procedure:**
  1. Subject fabric strips from waistband and leg cuffs to 500 stretch cycles at 60% elongation. Measure elastic recovery after 1 hour.
  2. Fit garments onto mannequins; execute 1,000 motorized walking/tossing sleep cycles. Measure displacement of waistband and leg cuffs from initial markings.
- **Acceptance Criteria:**
  - Fabric elastic recovery $\ge 92\%$ after 500 cycles (ASTM D3107).
  - Waistband vertical migration $< 1.0\text{ cm}$.
  - Leg cuff ride-up $< 1.0\text{ cm}$ (no rolling over thigh).
- **Failure Handling Protocol:**
  - *If Ride-Up $> 1.0\text{ cm}$:* Indicates leg binding tension too loose or inseam too short. Action: Extend inseam from 4.0" to 4.25" on plus sizes (2XL–4XL) and increase cuff mobilon width to 2.5 cm.

---

### PROTOCOL 7: THERMAL BREATHABILITY & MOISTURE VAPOR TRANSMISSION (MVTR)

- **Governing Standard:** ASTM E96 / E96M (Inverted Water Cup Method BW).
- **Equipment & Apparatus:**
  1. Environmental test chamber maintained at $38.0\pm 0.5^\circ\text{C}$ and $50\pm 2\%$ relative humidity.
  2. Vented permeability cups filled with distilled water, covered by test specimen with TPU membrane in direct contact with water (Inverted Cup Method BW).
  3. Analytical balance sensitive to 0.001 grams.
- **Step-by-Step Procedure:**
  1. Mount laminated gusset specimen over cup orifice and clamp tightly.
  2. Invert cup and place inside environmental chamber for 24 hours.
  3. Measure gravimetric weight loss ($\Delta M$) over 24 hours.
  4. Calculate MVTR: $\text{MVTR} = \frac{\Delta M}{A \times t} \times 24\text{ hours}$ (expressed in $\text{g/m}^2/\text{24h}$).
- **Acceptance Criteria:**
  - **All Variants (V1, V2, V3):** $\text{MVTR} \ge 3,000\text{ g/m}^2/\text{24h}$.
- **Failure Handling Protocol:**
  - *If MVTR $< 3,000\text{ g/m}^2/\text{24h}$:* Indicates excessive PUR adhesive coverage during lamination (solid glue film rather than breathable dot matrix). Action: Calibrate lamination gravure roller to reduce PUR glue weight to $10\text{–}12\text{ g/m}^2$.

---

### PROTOCOL 8: SEPARATED LAUNDERING & DURABILITY PROTOCOL

*To prevent invalid conflation of tests, laundering prep is separated from post-wash performance testing:*

```
                               LAUNDERING & DURABILITY WORKFLOW

       [RAW SPECIMEN]
             │
             ▼
       [AATCC 135: 50 LAUNDERING CYCLES] (Cold Wash 30°C, Standard Detergent, Line Dry)
             │
             ├───────────────────────┬───────────────────────┬───────────────────────┐
             ▼                       ▼                       ▼                       ▼
    [TEST 8A: DIMENSIONAL]  [TEST 8B: POST-WASH]    [TEST 8C: POST-WASH]    [TEST 8D: MEMBRANE]
    AATCC 135 Stability     ISO 9073-6 Capacity     AATCC 127 Hydrostatic   ASTM D2724 Peeling
    Length/Width < 3.0%     Retention ≥ 85%         Head ≥ 8,000 mm H2O     Zero Delamination
```

1. **Test 8A: Dimensional Stability After Home Laundering (AATCC 135 / ISO 6330):**
   - Measure bench markings before and after 5 cycles.
   - *Acceptance:* Dimensional shrinkage or elongation $< 3.0\%$ in both warp and weft directions.
2. **Test 8B: Post-Wash Absorbency Retention (ISO 9073-6 on 50-Cycle Specimens):**
   - Measure atmospheric fluid absorption after 50 cold wash cycles.
   - *Acceptance:* Retains $\ge 85\%$ of baseline unwashed fluid capacity ($\ge 55.2\text{ mL}$ for V3).
3. **Test 8C: Post-Wash Hydrostatic Resistance (AATCC 127 on 50-Cycle Specimens):**
   - Measure hydrostatic head over laminated gusset and sealed seams.
   - *Acceptance:* Hydrostatic head $\ge 8,000\text{ mm H}_2\text{O}$ with zero droplet breakthrough.
4. **Test 8D: Membrane Delamination & Visual Blister Rating (ASTM D2724 Visual):**
   - Inspect internal TPU film under $10\times$ optical magnification.
   - *Acceptance:* Zero visible blistering, peeling, tunnel formation, or pinholing.
- **Failure Handling Protocol:**
  - *If Delamination Occurs:* Indicates PUR adhesive bond failure. Action: Increase moisture-curing dwell time from 48 to 72 hours and verify adhesive cross-linking index before cutting.

---

### PROTOCOL 9: TEXTILE CHEMICAL SAFETY & PFAS COMPLIANCE

*Two-tier testing differentiating screening from regulatory speciation:*

> **Methodological Limitation Notice (ISO 20999:2026 / CIC Screening):**
> Total Fluorine (TF) screening via Oxygen Bomb Combustion Ion Chromatography (ISO 20999:2026 / CEN/TS 17043 / ASTM D7359) measures all fluorine atoms (organic and inorganic). **TF screening is NOT equivalent to proof of zero PFAS**, because it cannot distinguish regulated synthetic PFAS from benign inorganic fluorides (e.g., natural minerals, tap water fluoridation). If Total Fluorine is detected above the laboratory practical quantitation limit (typically ~10 ppm), the accredited testing laboratory **must recommend and execute complementary confirmatory testing** (Targeted LC-MS/MS covering 40+ EPA analytes and Extractable/Total Organic Fluorine [EOF/TOF]) to establish statutory compliance.
>
> **California AB 2515 Statutory Framework:**
> Under enacted California AB 2515 (Menstrual Products Right to Know and PFAS Prohibition Act), intentionally added PFAS is strictly prohibited effective January 1, 2025. Effective January 1, 2027, products are prohibited from containing regulated PFAS at or above practical quantitation limits or enforcement thresholds determined by the California Department of Toxic Substances Control (DTSC). No universal fixed 10 ppm statutory threshold applies until formal DTSC determination.

```
                               PFAS COMPLIANCE DECISION TREE

               [RAW FABRIC & FINISHED LAMINATE SPECIMEN]
                                   │
                                   ▼
               [TIER 1: TOTAL FLUORINE (TF) SCREENING]
               ISO 20999:2026 / CEN/TS 17043 / ASTM D7359
               (Oxygen Bomb Combustion Ion Chromatography)
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
             [TF Non-Detect]               [TF Detected]
             < Lab Quantitation Limit      ≥ Lab Reporting Limit (~10 ppm)
                    │                             │
                    ▼                             ▼
             [PASS SCREEN]                 [TIER 2: TARGETED PFAS SPECIATION]
             Proceed to Production         Targeted LC-MS/MS / GC-MS & TOF
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                             [Inorganic Fluoride Only]   [Regulated Synthetic PFAS]
                             e.g., minerals/salts        Synthetic fluorochemicals
                                    │                           │
                                    ▼                           ▼
                             [PASS AB 2515]              [FAIL & REJECT LOT]
                             Statutory compliance        Permanent disqualification
```

1. **Tier 1: Total Fluorine (TF) Screening (ISO 20999:2026 / CEN/TS 17043):**
   - Perform Oxygen Bomb Combustion Ion Chromatography (CIC) on raw fabrics and finished laminated composite.
   - *Limitation:* Serves as preliminary screening only; non-detect indicates absence of fluorine, whereas detection requires Tier 2 confirmatory analysis.
   - *Acceptance Target:* Below laboratory practical quantitation limit (typically $< 10\text{ ppm}$).
2. **Tier 2: Targeted PFAS Speciation & Complementary Testing (Mandatory if TF Detected):**
   - If screening detects total fluorine above quantitation limits, the laboratory must recommend and execute complementary testing: targeted liquid chromatography tandem mass spectrometry (LC-MS/MS) covering 40+ EPA PFAS analytes (including PFOA, PFOS, PFNA, GenX) and Extractable/Total Organic Fluorine (EOF/TOF).
   - *Acceptance Standards:*
     * California AB 2515: Zero intentionally added PFAS (effective Jan 1, 2025); compliance with any practical quantitation limit or enforcement threshold determined by DTSC (effective Jan 1, 2027).
     * California AB 1817: Total Organic Fluorine $< 100\text{ ppm}$ (effective 2025) / $< 50\text{ ppm}$ (effective 2027).
3. **Chemical Toxicology Screening (OEKO-TEX® Standard 100 Class II):**
   - Certified zero formaldehyde, banned azo dyes, extractable heavy metals, organotin compounds, or reproductive toxins.
- **Failure Handling Protocol:**
  - *If PFAS Detected:* Lot is **permanently rejected**. Supplier must identify contaminated yarn/finishing agent and re-source from certified fluorocarbon-free mills.

