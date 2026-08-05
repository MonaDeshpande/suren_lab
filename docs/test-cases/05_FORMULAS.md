# Formulas — Test Cases (Jaggery / Water / Basic Nutrition)

**Module:** Lab calculation library (32 catalog tests)  
**Related code:** `services/protocols/test_catalog.py`  
**Rounding:** 2 decimal places unless noted (SO₂, water mg/L, conductivity → 1 decimal)

Use Analyst UI **or** automated `tests/unit/test_formulas.py`.

**Families:** 11 Jaggery (food) · 11 Water · 11 Basic Nutrition (`bn_*`, shares `appearance` with Jaggery)

---

## Shared context for dry-basis tests

Unless testing override path, save moisture first with:

| Input | Value |
|-------|-------|
| w1 | 10.5 |
| w | 5.0 |
| w2 | 10.2 |

**Moisture %** = `(10.5 − 10.2) × 100 / 5` = **6.0**

For Basic Nutrition dry-basis tests, save **bn_moisture** first (same inputs → **6.0%**) or use ctx `bn_moisture=6.0`.

---

## TC-FOR-001 — Appearance (text)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Inputs** | `appearance_obs` = `Light brown crystalline` |
| **Expected** | Display = same text; numeric = null |

---

## TC-FOR-002 — Appearance missing observation

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Inputs** | empty `appearance_obs` |
| **Expected** | Error missing appearance_obs / required label |

---

## TC-FOR-003 — Moisture happy path

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `(W1 − W2) × 100 / W` |
| **Inputs** | w1=10.5, w2=10.2, w=5.0 |
| **Expected** | `6.0` / numeric 6.0 |

---

## TC-FOR-004 — Moisture W=0

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Inputs** | w=0, valid w1/w2 |
| **Expected** | `Sample weight W cannot be zero` |

---

## TC-FOR-005 — Total ash dry basis (with moisture ctx)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | Ash=`(W2−W1)×100/W`; Dry=`Ash×100/(100−moisture)` |
| **Inputs** | w1=20.0, w2=20.15, w=5.0; ctx moisture=6.0 |
| **Calc** | Ash=`(0.15)×100/5=3.0`; Dry=`3×100/94≈3.19` |
| **Expected** | `3.19` |

---

## TC-FOR-006 — Total ash missing moisture

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Inputs** | Valid weights; no ctx moisture; empty moisture_pct |
| **Expected** | Error requiring moisture / moisture_pct |

---

## TC-FOR-007 — Total ash moisture=100 invalid

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Boundary |
| **Inputs** | Valid weights; moisture=100 |
| **Expected** | `Invalid moisture for dry-basis conversion` |

---

## TC-FOR-008 — Acid insoluble ash dry basis

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Inputs** | w1=20.0, w2=20.05, w=5.0; moisture=6.0 |
| **Calc** | Insol=`1.0`; Dry=`1×100/94≈1.06` |
| **Expected** | `1.06` |

---

## TC-FOR-009 — Acid insoluble missing moisture

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Expected** | Moisture result required for dry-basis |

---

## TC-FOR-010 — Added color Present/Absent

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Inputs** | `color_result` = `Absent` |
| **Expected** | Display `Absent`; numeric null |

---

## TC-FOR-011 — Added color empty

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Expected** | Missing color_result |

---

## TC-FOR-012 — Extraneous matter dry basis

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `(W1−W2)×100/W` then dry basis |
| **Inputs** | w=10, w2_filter=1.0, w1_matter=1.2; moisture=6.0 |
| **Calc** | Ext=`2.0`; Dry=`2×100/94≈2.13` |
| **Expected** | `2.13` |

---

## TC-FOR-013 — Extraneous W=0

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Expected** | Sample weight W cannot be zero |

---

## TC-FOR-014 — Invert sugar dry basis

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `Conc×250×100/(Wt×B.R.)` then dry |
| **Inputs** | sugar_conc=0.5, sample_wt=5.0, br_invert=25.0; moisture=6.0 |
| **Calc** | Wet=`0.5×250×100/(5×25)=100`; Dry=`100×100/94≈106.38` |
| **Expected** | `106.38` |

---

## TC-FOR-015 — Invert sugar Wt or B.R. zero

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Inputs** | sample_wt=0 or br_invert=0 |
| **Expected** | Sample weight and B.R. must be non-zero |

---

## TC-FOR-016 — Reducing sugar dry basis

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `Conc×250×10/(Wt×B.R.)` then dry (Jaggery protocol) |
| **Inputs** | sugar_conc=0.5, sample_wt=5.0, br_reducing=50.0; moisture=6.0 |
| **Calc** | Wet=`0.5×250×10/(5×50)=5`; Dry=`5×100/94≈5.32` |
| **Expected** | `5.32` |

---

## TC-FOR-017 — Sucrose = (invert − reducing) × 0.95

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Inputs** | ctx invert_sugar=106.38, reducing_sugar=53.19 |
| **Calc** | `(106.38 − 53.19) × 0.95 ≈ 50.53` |
| **Expected** | `50.53` |

---

## TC-FOR-018 — Sucrose missing dependencies

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Inputs** | Empty ctx; empty invert_dry / reducing_dry |
| **Expected** | Need invert_sugar and reducing_sugar results |

---

## TC-FOR-019 — Sucrose with manual invert_dry / reducing_dry

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Inputs** | invert_dry=80, reducing_dry=30 |
| **Calc** | `(80 − 30) × 0.95 = 47.5` |
| **Expected** | `47.5` / `47.5` |

---

## TC-FOR-020 — Sulphated ash dry basis

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Inputs** | w1=20.0, w2=20.15, w=5.0; moisture=6.0 |
| **Expected** | Same pattern as total ash → `3.19` |

---

## TC-FOR-021 — Sulphur dioxide ppm

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `(µg SO₄ × 10) / Wt` |
| **Inputs** | ug_so4=25.0, sample_wt=5.0 |
| **Calc** | `250/5=50.0` → round 1 dp → `50.0` |
| **Expected** | `50.0` |

---

## TC-FOR-022 — Sulphur dioxide Wt=0

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Expected** | Sample weight cannot be zero |

---

## TC-FOR-023 — missing_required_inputs helper

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Positive |
| **Steps** | Call / exercise worksheet with only optional fields filled for moisture. |
| **Expected** | Labels for w1, w, w2 reported missing; optional empty_dish not required. |

---

## TC-FOR-024 — Invalid non-numeric input

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Type** | Negative |
| **Inputs** | w1=`abc` for moisture |
| **Expected** | Calculation fails (float parse / ValueError surfaced to user). |

---

## Water — TC-FOR-025…029

## TC-FOR-025 — Water conductivity (direct reading)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | Record conductivity reading (µS/cm) |
| **Inputs** | conductivity=450 |
| **Expected** | `450.0` |

---

## TC-FOR-026 — Water turbidity (direct reading)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | Record turbidity (NTU) |
| **Inputs** | turbidity=1.2 |
| **Expected** | `1.2` |

---

## TC-FOR-027 — Calcium as Ca

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `A × B × 1000 / volume` |
| **Inputs** | a=10.0, b=1.0, volume=50.0 |
| **Calc** | `10000/50=200.0` |
| **Expected** | `200.0` mg/L |

---

## TC-FOR-028 — Calcium as CaCO₃

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `A × C × 1000 / volume` |
| **Inputs** | a=10.0, c=2.0, volume=50.0 |
| **Calc** | `20000/50=400.0` |
| **Expected** | `400.0` mg/L |

---

## TC-FOR-029 — Calcium volume=0

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Inputs** | volume=0 for calcium_ca |
| **Expected** | Sample volume cannot be zero |

---

## Basic Nutrition — TC-FOR-030…037

## TC-FOR-030 — bn_total_ash (wet basis)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `(W2 − W1) × 100 / W` |
| **Inputs** | w1=20.0, w2=20.15, w=5.0 |
| **Calc** | `0.15×100/5=3.0` |
| **Expected** | `3.0` |

---

## TC-FOR-031 — bn_ash_insoluble_hcl (dry basis)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | Insol=`(W2−W1)×100/W`; Dry=`Insol×100/(100−bn_moisture)` |
| **Inputs** | w1=20.0, w2=20.05, w=5.0; ctx bn_moisture=6.0 |
| **Calc** | Insol=1.0; Dry≈1.06 |
| **Expected** | `1.06` |

---

## TC-FOR-032 — bn_ash_insoluble missing moisture

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Negative |
| **Inputs** | Valid w1/w2/w; no bn_moisture saved |
| **Expected** | bn_moisture result required for dry-basis |

---

## TC-FOR-033 — bn_crude_fibre

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | `(W2 − W1) × 100 / W` |
| **Inputs** | w=10.0, w1=20.0, w2=21.5 |
| **Expected** | `15.0` |

---

## TC-FOR-034 — bn_added_sugar (dry basis)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | Wet=`Conc×250×10/(Wt×B.R.)`; Dry=`Wet×100/(100−bn_moisture)` |
| **Inputs** | sugar_conc=0.5, sample_wt=5.0, br=50.0; ctx bn_moisture=6.0 |
| **Calc** | Wet=5.0; Dry≈5.32 |
| **Expected** | `5.32` |

---

## TC-FOR-035 — bn_total_sugar (dry basis)

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Positive |
| **Formula** | Wet=`Conc×250×100/(Wt×B.R.)`; Dry=`Wet×100/(100−bn_moisture)` |
| **Inputs** | sugar_conc=0.5, sample_wt=5.0, br=25.0; ctx bn_moisture=6.0 |
| **Calc** | Wet=100; Dry≈106.38 |
| **Expected** | `106.38` |

---

## TC-FOR-036 — Reducing sugar B.R.=0

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Inputs** | br_reducing=0 with valid conc/sample_wt |
| **Expected** | Sample weight and B.R. must be non-zero |

---

## TC-FOR-037 — bn_total_ash W=0

| Field | Value |
|-------|-------|
| **Priority** | P0 |
| **Type** | Boundary |
| **Inputs** | w=0 for bn_total_ash |
| **Expected** | Sample weight W cannot be zero |
