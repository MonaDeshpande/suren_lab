"""
services/protocols/test_catalog.py
----------------------------------
SHARED library of lab tests + formulas, tagged by sample category.

Reception picks Food / Water / Cattle Feed–Fertilizer; only matching tests
are offered. Selecting "Moisture" always uses the SAME inputs and formula.

Catalog: 11 Jaggery Food tests + 10 Basic Nutrition Food tests + 11 Water tests
+ 6 Micro tests.

Source of names/methods/worksheet fields:
  reference/Jaggery Protocol LLP.docx (Food / Jaggery)
  reference/Basic Nutrition Protocol 2026.docx (Food / Nutrition)
  reference/Water protocol 2025.docx (Water)
  reference/Micro Test Report.htm (Micro)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

# Stable category keys stored on request_samples.category
CATEGORY_FOOD = "food"
CATEGORY_WATER = "water"
CATEGORY_CATTLE_FEED_FERTILIZER = "cattle_feed_fertilizer"
CATEGORY_MICRO = "micro"

SAMPLE_CATEGORIES: dict[str, str] = {
    CATEGORY_FOOD: "Food",
    CATEGORY_WATER: "Water",
    CATEGORY_CATTLE_FEED_FERTILIZER: "Cattle Feed / Fertilizer",
    CATEGORY_MICRO: "Micro",
}

VALID_CATEGORIES = frozenset(SAMPLE_CATEGORIES.keys())

PROTOCOL_FAMILY_JAGGERY = "jaggery"
PROTOCOL_FAMILY_NUTRITION = "nutrition"

PROTEIN_TITRANT_HCL = "HCl"
PROTEIN_TITRANT_NAOH = "NaOH"
PROTEIN_TITRANTS = (PROTEIN_TITRANT_HCL, PROTEIN_TITRANT_NAOH)

# Shared symbolic formulas for all Basic / Detailed Nutrition tests (same text everywhere).
NUTRITION_FORMULA_DISPLAY: dict[str, str] = {
    "bn_moisture": "Moisture % = (W1 - W2) × 100 / W",
    "bn_total_ash": "Ash % = (W2 - W1) × 100 / W",
    "bn_total_fat": "Fat % = (W2 - W1) × 100 / W",
    "bn_carbohydrate": "Carbohydrate (%) = 100 − (Moisture + Ash + Fat + Protein)",
    "bn_calories": "Energy = 4×(protein + carbohydrate) + 9×fat",
    "bn_ash_insoluble_hcl": (
        "Ash insoluble in dil. HCl w/w (%) = (W2 − W1) × 100 / W ; "
        "Ash on dry basis (%) = Ash × 100 / (100 − Moisture)"
    ),
    "bn_crude_fibre": "Crude fibre % = (W2 - W1) × 100 / W",
    "bn_added_sugar": (
        "Added sugar (%) = Conc × 250 × 10 / (Wt × B.R.) ; "
        "Added sugar on dry basis (%) = Added sugar × 100 / (100 − Moisture)"
    ),
    "bn_total_sugar": (
        "Total sugar (%) = Conc × 250 × 100 / (Wt × B.R.) ; "
        "Total sugar on dry basis (%) = Total sugar × 100 / (100 − Moisture)"
    ),
}


def protein_titrant_from(inputs: dict[str, Any]) -> str:
    """Return HCl or NaOH; default NaOH for legacy saved rows without titrant."""
    raw = str(inputs.get("titrant") or PROTEIN_TITRANT_NAOH).strip()
    if raw.upper() in ("HCL", "HCl"):
        return PROTEIN_TITRANT_HCL
    return PROTEIN_TITRANT_NAOH


def protein_normality_key(titrant: str) -> str:
    return "n_hcl" if titrant == PROTEIN_TITRANT_HCL else "n_naoh"


def protein_normality_label(titrant: str) -> str:
    return "HCl" if titrant == PROTEIN_TITRANT_HCL else "NaOH"


def protein_formula_display(titrant: str = PROTEIN_TITRANT_NAOH) -> str:
    label = protein_normality_label(titrant)
    return (
        f"Nitrogen (%) = 0.014 × N({label}) × (B.R. Blank − B.R. Sample) × 100 / W ; "
        "Total Protein (%) = Nitrogen × Factor"
    )


def nutrition_formula_display(test_key: str, inputs: dict[str, Any] | None = None) -> str:
    """Human-readable formula for analyst UI and protocol (no internal bn_ keys)."""
    if test_key == "bn_protein":
        titrant = protein_titrant_from(inputs or {})
        return protein_formula_display(titrant)
    return NUTRITION_FORMULA_DISPLAY.get(test_key, "")


@dataclass
class InputField:
    """One reading the analyst must enter on a worksheet."""

    key: str           # stored in inputs_json
    label: str         # shown in UI
    unit: str = ""
    required: bool = True
    field_type: str = "number"  # number | text | choice
    choices: list[str] = field(default_factory=list)


@dataclass
class LabTest:
    """
    One catalog test — tagged for one or more sample categories.

    Attributes
    ----------
    key : stable id used in DB (e.g. moisture)
    name / method / unit : page-1 summary columns
    formula_display : human-readable formula shown to analyst
    inputs : worksheet fields
    calculate : function(inputs_dict, context) -> (display_str, numeric_or_None)
                context may include prior results (e.g. moisture %) for dry-basis
    categories : sample category keys that may select this test
    protocol_family : jaggery | nutrition — drives protocol Word template routing
    """

    key: str
    name: str
    method: str
    unit: str
    formula_display: str
    inputs: list[InputField]
    calculate: Callable[[dict[str, Any], dict[str, float]], tuple[str, Optional[float]]]
    categories: list[str] = field(default_factory=lambda: [CATEGORY_FOOD])
    protocol_family: str = PROTOCOL_FAMILY_JAGGERY

def _f(inputs: dict[str, Any], key: str) -> float:
    """Parse a required numeric input; raises ValueError if missing/invalid."""
    raw = inputs.get(key)
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"Missing value: {key}")
    return float(raw)


def _round(n: float, places: int = 2) -> float:
    return round(n, places)


# Tests that require a saved moisture result (or editable moisture_pct on worksheet).
DRY_BASIS_TEST_KEYS: frozenset[str] = frozenset(
    {
        "total_ash",
        "acid_insoluble_ash",
        "extraneous_matter",
        "invert_sugar",
        "reducing_sugar",
        "sulphated_ash",
        "bn_ash_insoluble_hcl",
        "bn_added_sugar",
        "bn_total_sugar",
    }
)

# Map dry-basis test → moisture result key in get_result_context().
MOISTURE_CTX_KEY: dict[str, str] = {
    "total_ash": "moisture",
    "acid_insoluble_ash": "moisture",
    "extraneous_matter": "moisture",
    "invert_sugar": "moisture",
    "reducing_sugar": "moisture",
    "sulphated_ash": "moisture",
    "bn_ash_insoluble_hcl": "bn_moisture",
    "bn_added_sugar": "bn_moisture",
    "bn_total_sugar": "bn_moisture",
}


def is_dry_basis_test(test_key: str) -> bool:
    return test_key in DRY_BASIS_TEST_KEYS


def moisture_ctx_key_for(test_key: str) -> Optional[str]:
    return MOISTURE_CTX_KEY.get(test_key)


def _resolve_moisture(
    inputs: dict[str, Any],
    ctx: dict[str, float],
    ctx_key: str = "moisture",
) -> float:
    """Worksheet moisture_pct (editable) overrides saved moisture from context."""
    if str(inputs.get("moisture_pct") or "").strip():
        return _f(inputs, "moisture_pct")
    if ctx.get(ctx_key) is not None:
        return float(ctx[ctx_key])
    raise ValueError(
        "MOISTURE_REQUIRED:Save the Moisture test before calculating this dry-basis test."
    )


def wet_value_for_test(test_key: str, inputs: dict[str, Any]) -> Optional[float]:
    """Intermediate wet-basis value before dry conversion, when applicable."""
    try:
        if test_key in ("total_ash", "acid_insoluble_ash", "sulphated_ash", "bn_ash_insoluble_hcl"):
            w1 = _f(inputs, "w1")
            w2 = _f(inputs, "w2")
            w = _f(inputs, "w")
            if w == 0:
                return None
            return round((w2 - w1) * 100.0 / w, 2)
        if test_key == "extraneous_matter":
            w = _f(inputs, "w")
            w2 = _f(inputs, "w2_filter")
            w1 = _f(inputs, "w1_matter")
            if w == 0:
                return None
            return round((w1 - w2) * 100.0 / w, 2)
        if test_key == "invert_sugar":
            return round(
                _sugar_percent(
                    _f(inputs, "sugar_conc"),
                    _f(inputs, "sample_wt"),
                    _f(inputs, "br_invert"),
                    factor=100.0,
                ),
                2,
            )
        if test_key == "reducing_sugar":
            return round(
                _sugar_percent(
                    _f(inputs, "sugar_conc"),
                    _f(inputs, "sample_wt"),
                    _f(inputs, "br_reducing"),
                    factor=10.0,
                ),
                2,
            )
        if test_key == "bn_added_sugar":
            return round(
                _sugar_percent(
                    _f(inputs, "sugar_conc"),
                    _f(inputs, "sample_wt"),
                    _f(inputs, "br"),
                    factor=10.0,
                ),
                2,
            )
        if test_key == "bn_total_sugar":
            return round(
                _sugar_percent(
                    _f(inputs, "sugar_conc"),
                    _f(inputs, "sample_wt"),
                    _f(inputs, "br"),
                    factor=100.0,
                ),
                2,
            )
    except ValueError:
        return None
    return None


# ---------------------------------------------------------------------------
# Calculators — same math for every sample that selects this test
# ---------------------------------------------------------------------------

def _calc_appearance(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    text = str(inputs.get("appearance_obs") or "").strip()
    if not text:
        raise ValueError("Missing value: appearance_obs")
    return text, None


def _calc_moisture(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    # Moisture % = (W1 - W2) * 100 / W
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    moisture = _round((w1 - w2) * 100.0 / w)
    return f"{moisture}", moisture


def _calc_total_ash(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    # Ash % = (W2 - W1) * 100 / W
    # Dry basis = Ash * 100 / (100 - moisture)
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    ash = (w2 - w1) * 100.0 / w
    moisture = _resolve_moisture(inputs, ctx, "moisture")
    if (100.0 - moisture) == 0:
        raise ValueError("Invalid moisture for dry-basis conversion")
    dry = _round(ash * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_acid_insoluble(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    insol = (w2 - w1) * 100.0 / w
    moisture = _resolve_moisture(inputs, ctx, "moisture")
    dry = _round(insol * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_added_color(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    val = str(inputs.get("color_result") or "").strip()
    if not val:
        raise ValueError("Missing value: color_result")
    return val, None


def _calc_extraneous(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    # Extraneous % = (W1 - W2) * 100 / W ; dry basis with moisture
    w = _f(inputs, "w")
    w2 = _f(inputs, "w2_filter")
    w1 = _f(inputs, "w1_matter")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    ext = (w1 - w2) * 100.0 / w
    moisture = _resolve_moisture(inputs, ctx, "moisture")
    dry = _round(ext * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _sugar_percent(
    concentration: float,
    sample_wt: float,
    br: float,
    factor: float = 100.0,
) -> float:
    # Concentration(g) * 250 * factor / (Wt * B.R.)
    # Invert uses factor=100; reducing uses factor=10 (Jaggery protocol).
    if sample_wt == 0 or br == 0:
        raise ValueError("Sample weight and B.R. must be non-zero")
    return concentration * 250.0 * factor / (sample_wt * br)


def _calc_invert_sugar(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    conc = _f(inputs, "sugar_conc")
    w = _f(inputs, "sample_wt")
    br = _f(inputs, "br_invert")
    wet = _sugar_percent(conc, w, br, factor=100.0)
    moisture = _resolve_moisture(inputs, ctx, "moisture")
    dry = _round(wet * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_reducing_sugar(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    conc = _f(inputs, "sugar_conc")
    w = _f(inputs, "sample_wt")
    br = _f(inputs, "br_reducing")
    # Protocol: Conc × 250 × 10 / (Wt × B.R.), then dry basis
    wet = _sugar_percent(conc, w, br, factor=10.0)
    moisture = _resolve_moisture(inputs, ctx, "moisture")
    dry = _round(wet * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_sucrose(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    # Sucrose (dry) = (Invert sugar − Reducing sugar) × 0.95
    inv = ctx.get("invert_sugar")
    red = ctx.get("reducing_sugar")
    if inv is None and str(inputs.get("invert_dry") or "").strip():
        inv = _f(inputs, "invert_dry")
    if red is None and str(inputs.get("reducing_dry") or "").strip():
        red = _f(inputs, "reducing_dry")
    if inv is None or red is None:
        raise ValueError(
            "Need invert_sugar and reducing_sugar results "
            "(save those tests first, or enter invert_dry / reducing_dry)"
        )
    sucrose = _round((inv - red) * 0.95)
    return f"{sucrose}", sucrose


def _calc_sulphated_ash(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    ash = (w2 - w1) * 100.0 / w
    moisture = _resolve_moisture(inputs, ctx, "moisture")
    dry = _round(ash * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_so2(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    # ppm = (µg SO4 from graph * 10) / wt of sample
    ug = _f(inputs, "ug_so4")
    wt = _f(inputs, "sample_wt")
    if wt == 0:
        raise ValueError("Sample weight cannot be zero")
    ppm = _round(ug * 10.0 / wt, 1)
    return f"{ppm}", ppm


# ---------------------------------------------------------------------------
# Water calculators — reference/Water protocol 2025.docx
# ---------------------------------------------------------------------------

def _calc_ph(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    val = _round(_f(inputs, "ph_value"), 2)
    return f"{val}", val


def _calc_tds(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    w = _f(inputs, "w")
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    if w == 0:
        raise ValueError("Volume of sample W cannot be zero")
    tds = _round((w2 - w1) * 1000.0 * 1000.0 / w, 1)
    return f"{tds}", tds


def _calc_chlorides(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    v3 = _f(inputs, "v3")
    v1 = _f(inputs, "v1")
    v2 = _f(inputs, "v2")
    n = _f(inputs, "n")
    if v3 == 0:
        raise ValueError("Volume V3 cannot be zero")
    result = _round((v1 - v2) * n * 35.45 * 1000.0 / v3, 1)
    return f"{result}", result


def _calc_total_alkalinity(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    v = _f(inputs, "v")
    a = _f(inputs, "a")
    n = _f(inputs, "n")
    if v == 0:
        raise ValueError("Volume V cannot be zero")
    result = _round(a * n * 50000.0 / v, 1)
    return f"{result}", result


def _calc_conductivity(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    val = _round(_f(inputs, "conductivity"), 1)
    return f"{val}", val


def _calc_total_hardness(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    volume = _f(inputs, "volume")
    a = _f(inputs, "a")
    b = _f(inputs, "b")
    if volume == 0:
        raise ValueError("Sample volume cannot be zero")
    result = _round(a * b * 1000.0 / volume, 1)
    return f"{result}", result


def _calc_calcium_ca(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    volume = _f(inputs, "volume")
    a = _f(inputs, "a")
    b = _f(inputs, "b")
    if volume == 0:
        raise ValueError("Sample volume cannot be zero")
    result = _round(a * b * 1000.0 / volume, 1)
    return f"{result}", result


def _calc_calcium_caco3(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    volume = _f(inputs, "volume")
    a = _f(inputs, "a")
    c = _f(inputs, "c")
    if volume == 0:
        raise ValueError("Sample volume cannot be zero")
    result = _round(a * c * 1000.0 / volume, 1)
    return f"{result}", result


def _calc_magnesium(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    hardness = ctx.get("total_hardness")
    calcium_caco3 = ctx.get("calcium_caco3")
    if hardness is None and str(inputs.get("total_hardness") or "").strip():
        hardness = _f(inputs, "total_hardness")
    if calcium_caco3 is None and str(inputs.get("calcium_caco3") or "").strip():
        calcium_caco3 = _f(inputs, "calcium_caco3")
    if hardness is None or calcium_caco3 is None:
        raise ValueError(
            "Need total_hardness and calcium_caco3 results "
            "(save those tests first, or enter overrides)"
        )
    result = _round((hardness - calcium_caco3) * 0.243, 1)
    return f"{result}", result


def _calc_odor(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    text = str(inputs.get("odor_obs") or "").strip()
    if not text:
        raise ValueError("Missing value: odor_obs")
    return text, None


def _calc_turbidity(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    val = _round(_f(inputs, "turbidity"), 1)
    return f"{val}", val


def _calc_micro_result(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    """Micro tests: analyst enters result value (unit stored separately)."""
    text = str(
        inputs.get("result_value") or inputs.get("result_obs") or ""
    ).strip()
    if not text:
        raise ValueError("Missing value: result_value")
    return text, None


# Water protocol micro last page — reference/WhatsApp Image 2026-08-05 at 10.56.20 PM.jpeg
WATER_TOTAL_COLIFORM_DEFAULT_PROCEDURE = (
    "Filter 100 ml of the Water sample to be using a membrane filter on "
    "membrane filter assembly. Place the filter on the HiCrome Coliform agar "
    "media Petri Plates. Incubate at 37° C for 48 hrs. After Incubation take "
    "Kovac's Indole Reagent put it on colonies 2-3 drops if pink to converted "
    "cherry red color then biochemical indole confirmatory test in the total "
    "coliform is present if color is not changes total coliform is absent"
)

WATER_E_COLI_DEFAULT_PROCEDURE = (
    "Filter 100 ml of the Water sample to be using a membrane filter on "
    "membrane filter assembly Place the filter on the HiCrome Coliform agar "
    "medium Petri Plate Incubate at 37° C for 48 hrs After Incubation take "
    "Kovac's Indole Reagent put it on colonies 2-3 drops Blue color colonies "
    "to see on plates then E. coli is present"
)

WATER_MICRO_DEFAULT_PROCEDURES: dict[str, str] = {
    "water_total_coliform": WATER_TOTAL_COLIFORM_DEFAULT_PROCEDURE,
    "water_e_coli": WATER_E_COLI_DEFAULT_PROCEDURE,
}


def default_water_micro_procedure(test_key: str) -> str:
    """Return the catalog default procedure text for a water micro test."""
    return WATER_MICRO_DEFAULT_PROCEDURES.get(test_key, "")


# ---------------------------------------------------------------------------
# Basic Nutrition calculators — reference/Basic Nutrition Protocol 2026.docx
# ---------------------------------------------------------------------------

def _bn_moisture_pct(inputs: dict, ctx: dict) -> Optional[float]:
    if str(inputs.get("moisture_pct") or "").strip():
        return _f(inputs, "moisture_pct")
    if ctx.get("bn_moisture") is not None:
        return float(ctx["bn_moisture"])
    return None


def _calc_bn_moisture(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    moisture = _round((w1 - w2) * 100.0 / w)
    return f"{moisture}", moisture


def _calc_bn_total_ash(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    ash = _round((w2 - w1) * 100.0 / w)
    return f"{ash}", ash


def _calc_bn_total_fat(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    w = _f(inputs, "w")
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    fat = _round((w2 - w1) * 100.0 / w)
    return f"{fat}", fat


def _calc_bn_protein(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    # Reference: Nitrogen = 0.014 × N(titrant) × (BR blank − BR sample) × 100 / W
    #            Protein = Nitrogen × Factor
    w = _f(inputs, "w")
    titrant = protein_titrant_from(inputs)
    norm_key = protein_normality_key(titrant)
    norm_label = protein_normality_label(titrant)
    if not str(inputs.get(norm_key) or "").strip():
        raise ValueError(f"Normality of {norm_label} is required when titrant is {titrant}")
    n_titrant = _f(inputs, norm_key)
    br_blank = _f(inputs, "br_blank")
    br_sample = _f(inputs, "br_sample")
    n_factor = _f(inputs, "n_factor")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    nitrogen = 0.014 * n_titrant * (br_blank - br_sample) * 100.0 / w
    protein = _round(nitrogen * n_factor)
    return f"{protein}", protein


def _macro_from_ctx_or_inputs(
    inputs: dict,
    ctx: dict,
    ctx_key: str,
    input_key: str,
) -> Optional[float]:
    if ctx.get(ctx_key) is not None:
        return float(ctx[ctx_key])
    if str(inputs.get(input_key) or "").strip():
        return _f(inputs, input_key)
    return None


def _calc_bn_carbohydrate(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    # Reference: 100 − (Moisture + Ash + Fat + Protein)
    moisture = _macro_from_ctx_or_inputs(inputs, ctx, "bn_moisture", "moisture_pct")
    protein = _macro_from_ctx_or_inputs(inputs, ctx, "bn_protein", "protein_pct")
    fat = _macro_from_ctx_or_inputs(inputs, ctx, "bn_total_fat", "fat_pct")
    ash = _macro_from_ctx_or_inputs(inputs, ctx, "bn_total_ash", "ash_pct")
    if None in (moisture, protein, fat, ash):
        raise ValueError(
            "Need Moisture, Protein, Total Fat, and Total Ash results "
            "(save those first, or enter overrides)"
        )
    carb = _round(100.0 - moisture - protein - fat - ash)
    return f"{carb}", carb


def _calc_bn_calories(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    # IS 9487: 4×(protein+carbohydrate) + 9×fat (Kcal/100g)
    protein = _macro_from_ctx_or_inputs(inputs, ctx, "bn_protein", "protein_pct")
    carb = _macro_from_ctx_or_inputs(inputs, ctx, "bn_carbohydrate", "carb_pct")
    fat = _macro_from_ctx_or_inputs(inputs, ctx, "bn_total_fat", "fat_pct")
    if None in (protein, carb, fat):
        raise ValueError(
            "Need Protein, Carbohydrate, and Total Fat results "
            "(save those first, or enter overrides)"
        )
    kcal = _round(4.0 * (protein + carb) + 9.0 * fat, 1)
    return f"{kcal}", kcal


def _calc_bn_ash_insoluble_hcl(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    insol = (w2 - w1) * 100.0 / w
    moisture = _resolve_moisture(inputs, ctx, "bn_moisture")
    if (100.0 - moisture) == 0:
        raise ValueError("Invalid moisture for dry-basis conversion")
    dry = _round(insol * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_bn_crude_fibre(inputs: dict, _ctx: dict) -> tuple[str, Optional[float]]:
    w = _f(inputs, "w")
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    fibre = _round((w2 - w1) * 100.0 / w)
    return f"{fibre}", fibre


def _calc_bn_sugar(inputs: dict, ctx: dict, *, factor: float, moisture_key: str) -> tuple[str, Optional[float]]:
    conc = _f(inputs, "sugar_conc")
    w = _f(inputs, "sample_wt")
    br = _f(inputs, "br")
    wet = _sugar_percent(conc, w, br, factor=factor)
    moisture = _resolve_moisture(inputs, ctx, moisture_key)
    dry = _round(wet * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_bn_added_sugar(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    return _calc_bn_sugar(inputs, ctx, factor=10.0, moisture_key="bn_moisture")


def _calc_bn_total_sugar(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    return _calc_bn_sugar(inputs, ctx, factor=100.0, moisture_key="bn_moisture")


# ---------------------------------------------------------------------------
# Catalog — order matches protocol page-1 table
# ---------------------------------------------------------------------------

TEST_CATALOG: dict[str, LabTest] = {
    "appearance": LabTest(
        key="appearance",
        name="Appearance",
        method="Visual observation",
        unit="",
        formula_display="Record observed appearance (text).",
        inputs=[
            InputField("appearance_obs", "Appearance observation", "", True, "text"),
        ],
        calculate=_calc_appearance,
    ),
    "moisture": LabTest(
        key="moisture",
        name="Moisture",
        method="IS 15279:2003",
        unit="%",
        formula_display="Moisture % = (W1 - W2) × 100 / W",
        inputs=[
            InputField("empty_dish", "Weight of empty stainless steel dish (gms)", "g", False),
            InputField("w1", "Weight of dish + Sample before drying (W1)", "g"),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_dry", "Weight of dish + Sample after drying", "g", False),
            InputField("w2", "Weight of dish + Sample after drying (W2)", "g"),
        ],
        calculate=_calc_moisture,
    ),
    "total_ash": LabTest(
        key="total_ash",
        name="Total ash on dry basis",
        method="Clause 9.3 of FSSAI Manual for sugar and sugar products and confectionary products :2015",
        unit="%",
        formula_display="Ash w/w (%) = (W2 − W1) × 100 / W ; Ash on dry basis (%) = Ash × 100 / (100 − Moisture)",
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Sample before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Sample after ignition", "g", False),
            InputField("w2", "Weight of dish + Sample after ignition (W2)", "g"),
        ],
        calculate=_calc_total_ash,
    ),
    "acid_insoluble_ash": LabTest(
        key="acid_insoluble_ash",
        name="Ash Insoluble in dilute HCL on dry basis",
        method="IS 12923:1990",
        unit="%",
        formula_display="Insoluble ash w/w (%) = (W2 − W1) × 100 / W ; Insoluble ash on dry basis (%) = Insoluble ash × 100 / (100 − Moisture)",
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Insoluble ash before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Insoluble ash after ignition", "g", False),
            InputField("w2", "Weight of dish + Insoluble ash after ignition (W2)", "g"),
        ],
        calculate=_calc_acid_insoluble,
    ),
    "added_color": LabTest(
        key="added_color",
        name="Added Color",
        method="FSSAI Manual for Food Additives : 2016",
        unit="",
        formula_display="Record Present or Absent.",
        inputs=[
            InputField(
                "color_result",
                "Added Color",
                "",
                True,
                "choice",
                ["Present", "Absent"],
            ),
        ],
        calculate=_calc_added_color,
    ),
    "extraneous_matter": LabTest(
        key="extraneous_matter",
        name="Extraneous matter Insoluble in water on dry basis",
        method="Clause 9.2 of FSSAI Manual of Beverages, Sugar and Confectionary products :2015",
        unit="%",
        formula_display="Extraneous matter (%) = (W1 − W2) × 100 / W ; Extraneous matter (on dry basis) = Extraneous matter × 100 / (100 − Moisture)",
        inputs=[
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("w2_filter", "Weight of Filter Paper (W2)", "g"),
            InputField("w1_matter", "Weight of Filter Paper + Dry Extraneous matter (W1)", "g"),
        ],
        calculate=_calc_extraneous,
    ),
    "invert_sugar": LabTest(
        key="invert_sugar",
        name="Total sugar expressed as Invert sugar on dry weight basis",
        method="IS:15279 : 2003",
        unit="%",
        formula_display="Total invert sugar (%) = Conc × 250 × 100 / (Wt × B.R.) ; Total invert sugar on dry basis (%) = Invert sugar × 100 / (100 − Moisture)",
        inputs=[
            InputField("sample_wt", "Amount of sample taken (gms)", "g"),
            InputField("fehling_invert", "Fehling solution for Total Invert sugar", "ml", False),
            InputField("br_invert", "B.R. reading for invert sugar", "ml"),
            InputField("sugar_conc", "Concentration of sugar (g)", "g"),
        ],
        calculate=_calc_invert_sugar,
    ),
    "reducing_sugar": LabTest(
        key="reducing_sugar",
        name="Total sugar expressed as Reduced sugar (on dry basis)",
        method="IS:15279 : 2003",
        unit="%",
        formula_display="Total reducing sugar (%) = Conc × 250 × 10 / (Wt × B.R.) ; Total reducing sugar on dry basis (%) = Reducing sugar × 100 / (100 − Moisture)",
        inputs=[
            InputField("sample_wt", "Amount of sample taken (gms)", "g"),
            InputField("fehling_reducing", "Fehling solution for Reducing sugar", "ml", False),
            InputField("br_reducing", "B.R. reading for reducing sugar", "ml"),
            InputField("sugar_conc", "Concentration of sugar (g)", "g"),
        ],
        calculate=_calc_reducing_sugar,
    ),
    "sucrose": LabTest(
        key="sucrose",
        name="Sucrose % on dry basis",
        method="IS:15279 : 2018",
        unit="%",
        formula_display="Sucrose (dry) % = (Invert sugar - Reducing sugar) × 0.95",
        inputs=[
            InputField("invert_dry", "Invert sugar dry % (if not saved)", "%", False),
            InputField("reducing_dry", "Reducing sugar dry % (if not saved)", "%", False),
        ],
        calculate=_calc_sucrose,
    ),
    "sulphated_ash": LabTest(
        key="sulphated_ash",
        name="Sulphated ash on dry basis",
        method="IS:15279 : 2003",
        unit="%",
        formula_display="Sulphated ash w/w (%) = (W2 − W1) × 100 / W ; Sulphated ash on dry basis (%) = Sulphated ash × 100 / (100 − Moisture)",
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Sample before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Sample after ignition", "g", False),
            InputField("w2", "Weight of dish + Sample after ignition (W2)", "g"),
        ],
        calculate=_calc_sulphated_ash,
    ),
    "sulphur_dioxide": LabTest(
        key="sulphur_dioxide",
        name="Sulphur dioxide",
        method="IS:15279 : 2003",
        unit="ppm",
        formula_display="SO₂ (ppm) = (µg SO₄ from graph × 10) / Wt of sample",
        inputs=[
            InputField("sample_wt", "Wt. of Sample", "g"),
            InputField("ug_so4", "µg SO₄ from graph", "µg"),
        ],
        calculate=_calc_so2,
    ),
    # --- Basic Nutrition (reference/Basic Nutrition Protocol 2026.docx) ---
    "bn_moisture": LabTest(
        key="bn_moisture",
        name="Moisture",
        method="Clause 5 Of IS 12711",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_moisture"],
        inputs=[
            InputField("empty_dish", "Weight of empty stainless steel dish (gms)", "g", False),
            InputField("w1", "Weight of dish + Sample before drying (W1)", "g"),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_dry", "Weight of dish + Sample after drying", "g", False),
            InputField("w2", "Weight of dish + Sample after drying (W2)", "g"),
        ],
        calculate=_calc_bn_moisture,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_total_ash": LabTest(
        key="bn_total_ash",
        name="Total Ash",
        method="Clause 6 Of Is 12711",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_total_ash"],
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Sample before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Sample after ignition", "g", False),
            InputField("w2", "Weight of dish + Sample after ignition (W2)", "g"),
        ],
        calculate=_calc_bn_total_ash,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_total_fat": LabTest(
        key="bn_total_fat",
        name="Total Fat",
        method="Clause 10 Of IS 12711",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_total_fat"],
        inputs=[
            InputField("w", "Wt. of sample taken (W)", "g"),
            InputField("w1", "Wt. of empty Evaporating Dish (W1)", "g"),
            InputField("w2", "Wt. of fat + Evaporating Dish (W2)", "g"),
        ],
        calculate=_calc_bn_total_fat,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_protein": LabTest(
        key="bn_protein",
        name="Protein",
        method="IS 7219",
        unit="%",
        formula_display=protein_formula_display(PROTEIN_TITRANT_NAOH),
        inputs=[
            InputField(
                "titrant",
                "Titrant used",
                "",
                True,
                "choice",
                list(PROTEIN_TITRANTS),
            ),
            InputField("w", "Wt. of sample taken (W)", "g"),
            InputField("n_naoh", "Normality of NaOH", "", False),
            InputField("n_hcl", "Normality of HCl", "", False),
            InputField("br_blank", "B.R. For Blank", "ml"),
            InputField("br_sample", "B.R. For Sample", "ml"),
            InputField(
                "n_factor",
                "Protein N-factor (6.38 milk / 5.70 cereals / 6.25 general / 5.55 gelatin)",
                "",
            ),
        ],
        calculate=_calc_bn_protein,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_carbohydrate": LabTest(
        key="bn_carbohydrate",
        name="Carbohydrate",
        method="IS 1656",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_carbohydrate"],
        inputs=[
            InputField("moisture_pct", "Moisture % (if not saved)", "%", False),
            InputField("protein_pct", "Protein % (if not saved)", "%", False),
            InputField("fat_pct", "Total Fat % (if not saved)", "%", False),
            InputField("ash_pct", "Total Ash % (if not saved)", "%", False),
        ],
        calculate=_calc_bn_carbohydrate,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_calories": LabTest(
        key="bn_calories",
        name="Calories (Energy)",
        method="IS 9487",
        unit="Kcal/100g",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_calories"],
        inputs=[
            InputField("protein_pct", "Protein % (if not saved)", "%", False),
            InputField("carb_pct", "Carbohydrate % (if not saved)", "%", False),
            InputField("fat_pct", "Total Fat % (if not saved)", "%", False),
        ],
        calculate=_calc_bn_calories,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_ash_insoluble_hcl": LabTest(
        key="bn_ash_insoluble_hcl",
        name="Ash Insoluble in HCL",
        method="IS 1797",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_ash_insoluble_hcl"],
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Insoluble ash before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Insoluble ash after ignition", "g", False),
            InputField("w2", "Weight of dish + Insoluble ash after ignition (W2)", "g"),
        ],
        calculate=_calc_bn_ash_insoluble_hcl,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_crude_fibre": LabTest(
        key="bn_crude_fibre",
        name="Crude Fibre",
        method="FSSAI Manual Of Cereal & Cereal Prod. 2023",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_crude_fibre"],
        inputs=[
            InputField("w", "Wt. of sample taken (W)", "g"),
            InputField("w1", "Wt. of empty filter paper (W1)", "g"),
            InputField("w2", "Wt. of Fiber + filter paper (W2) - Ash", "g"),
        ],
        calculate=_calc_bn_crude_fibre,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_added_sugar": LabTest(
        key="bn_added_sugar",
        name="Added Sugar",
        method="IS 15279",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_added_sugar"],
        inputs=[
            InputField("sample_wt", "Amount of sample taken (gms)", "g"),
            InputField("fehling", "Fehling solution for Reducing sugar", "ml", False),
            InputField("br", "B.R. reading for reducing sugar", "ml"),
            InputField("sugar_conc", "Concentration of sugar (g)", "g"),
        ],
        calculate=_calc_bn_added_sugar,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    "bn_total_sugar": LabTest(
        key="bn_total_sugar",
        name="Total Sugar",
        method="IS 15279",
        unit="%",
        formula_display=NUTRITION_FORMULA_DISPLAY["bn_total_sugar"],
        inputs=[
            InputField("sample_wt", "Amount of sample taken (gms)", "g"),
            InputField("fehling", "Fehling solution for Total Invert sugar", "ml", False),
            InputField("br", "B.R. reading for invert sugar", "ml"),
            InputField("sugar_conc", "Concentration of sugar (g)", "g"),
        ],
        calculate=_calc_bn_total_sugar,
        protocol_family=PROTOCOL_FAMILY_NUTRITION,
    ),
    # --- Water (reference/Water protocol 2025.docx) ---
    "ph": LabTest(
        key="ph",
        name="pH (at 25°C)",
        method="IS 3025 : Part 11",
        unit="",
        formula_display="Record pH at 25°C.",
        inputs=[InputField("ph_value", "pH at 25°C", "")],
        calculate=_calc_ph,
        categories=[CATEGORY_WATER],
    ),
    "tds": LabTest(
        key="tds",
        name="Total Dissolved Solids (TDS)",
        method="IS 3025 : Part 16",
        unit="mg/L",
        formula_display="TDS (mg/L) = (W2 - W1) × 1000 × 1000 / W",
        inputs=[
            InputField("w", "Volume of sample taken (W)", "mL"),
            InputField("w1", "Weight of Empty Dish (W1)", "g"),
            InputField("w2", "Weight of Dissolved Solids + Dish (W2)", "g"),
        ],
        calculate=_calc_tds,
        categories=[CATEGORY_WATER],
    ),
    "chlorides": LabTest(
        key="chlorides",
        name="Chlorides as Cl",
        method="IS 3025 : Part 32",
        unit="mg/L",
        formula_display="Chloride (mg/L) = (V1 - V2) × N × 35.45 × 1000 / V3",
        inputs=[
            InputField("v3", "Volume of sample taken (V3)", "mL"),
            InputField("v1", "Burette reading of sample (V1)", "mL"),
            InputField("v2", "Burette reading of Blank (V2)", "mL"),
            InputField("n", "Normality of AgNO3 (N)", ""),
        ],
        calculate=_calc_chlorides,
        categories=[CATEGORY_WATER],
    ),
    "total_alkalinity": LabTest(
        key="total_alkalinity",
        name="Total Alkalinity as CaCO₃",
        method="IS 3025 : Part 23",
        unit="mg/L",
        formula_display="Alkalinity (mg/L) as CaCO₃ = A × N × 50000 / V",
        inputs=[
            InputField("v", "Volume of sample taken (V)", "mL"),
            InputField("a", "Burette reading (A)", "mL"),
            InputField("n", "Normality of sulphuric acid (N)", ""),
        ],
        calculate=_calc_total_alkalinity,
        categories=[CATEGORY_WATER],
    ),
    "conductivity": LabTest(
        key="conductivity",
        name="Conductivity at 25°C",
        method="IS 3025 : Part 14",
        unit="µs/cm",
        formula_display="Record conductivity at 25°C.",
        inputs=[InputField("conductivity", "Conductivity at 25°C", "µs/cm")],
        calculate=_calc_conductivity,
        categories=[CATEGORY_WATER],
    ),
    "total_hardness": LabTest(
        key="total_hardness",
        name="Total Hardness as CaCO₃",
        method="IS 3025 : Part 21",
        unit="mg/L",
        formula_display="Hardness (mg/L) as CaCO₃ = A × B × 1000 / ml of sample",
        inputs=[
            InputField("volume", "Volume of sample taken", "mL"),
            InputField("a", "Burette reading (A)", "mL"),
            InputField("b", "1 ml 0.01 M EDTA = mg of CaCO₃ (B)", "mg"),
        ],
        calculate=_calc_total_hardness,
        categories=[CATEGORY_WATER],
    ),
    "calcium_ca": LabTest(
        key="calcium_ca",
        name="Calcium as Ca",
        method="IS 3025 : Part 40",
        unit="mg/L",
        formula_display="Calcium (mg/L) as Ca = A × B × 1000 / ml of sample",
        inputs=[
            InputField("volume", "Volume of sample taken", "mL"),
            InputField("a", "Burette reading (A)", "mL"),
            InputField("b", "1 ml 0.01 M EDTA = mg of Ca (B)", "mg"),
        ],
        calculate=_calc_calcium_ca,
        categories=[CATEGORY_WATER],
    ),
    "calcium_caco3": LabTest(
        key="calcium_caco3",
        name="Calcium as CaCO₃",
        method="IS 3025 : Part 40",
        unit="mg/L",
        formula_display="Calcium (mg/L) as CaCO₃ = A × C × 1000 / ml of sample",
        inputs=[
            InputField("volume", "Volume of sample taken", "mL"),
            InputField("a", "Burette reading (A)", "mL"),
            InputField("c", "1 ml 0.01 M EDTA = mg of CaCO₃ (C)", "mg"),
        ],
        calculate=_calc_calcium_caco3,
        categories=[CATEGORY_WATER],
    ),
    "magnesium": LabTest(
        key="magnesium",
        name="Magnesium as Mg",
        method="IS 3025 : Part 46",
        unit="mg/L",
        formula_display="Mg (mg/L) = (Total Hardness as CaCO₃ - Calcium as CaCO₃) × 0.243",
        inputs=[
            InputField("total_hardness", "Total Hardness as CaCO₃ (if not saved)", "mg/L", False),
            InputField("calcium_caco3", "Calcium as CaCO₃ (if not saved)", "mg/L", False),
        ],
        calculate=_calc_magnesium,
        categories=[CATEGORY_WATER],
    ),
    "odor": LabTest(
        key="odor",
        name="Odor",
        method="IS 3025 : Part 5",
        unit="",
        formula_display="Record observed odour (text).",
        inputs=[InputField("odor_obs", "Odour observation", "", True, "text")],
        calculate=_calc_odor,
        categories=[CATEGORY_WATER],
    ),
    "turbidity": LabTest(
        key="turbidity",
        name="Turbidity",
        method="IS 3025 : Part 10",
        unit="NTU",
        formula_display="Record turbidity (NTU).",
        inputs=[InputField("turbidity", "Turbidity", "NTU")],
        calculate=_calc_turbidity,
        categories=[CATEGORY_WATER],
    ),
    # --- Water micro (last Observation Table page on water protocol) ---
    "water_total_coliform": LabTest(
        key="water_total_coliform",
        name="Total Coliform",
        method="",
        unit="",
        formula_display="Enter observed result (e.g. present, absent).",
        inputs=[
            InputField(
                "procedure",
                "Procedure",
                "",
                True,
                "text",
            ),
            InputField("result_obs", "Result", "", True, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_WATER],
    ),
    "water_e_coli": LabTest(
        key="water_e_coli",
        name="E. coli",
        method="",
        unit="",
        formula_display="Enter observed result (e.g. present, absent).",
        inputs=[
            InputField(
                "procedure",
                "Procedure",
                "",
                True,
                "text",
            ),
            InputField("result_obs", "Result", "", True, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_WATER],
    ),
    # --- Micro (reference/Micro Test Report.htm) ---
    "total_plate_count": LabTest(
        key="total_plate_count",
        name="Total Plate Count",
        method="IS:5402:2018",
        unit="",
        formula_display="Enter observed result (e.g. 3.0 x 10³).",
        inputs=[
            InputField("result_value", "Result", "", True, "text"),
            InputField("result_unit", "Unit", "", False, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_MICRO],
    ),
    "t_coliform": LabTest(
        key="t_coliform",
        name="T.coliform",
        method="IS 5401(Part-2):2018",
        unit="",
        formula_display="Enter observed result (e.g. Absent, <1.0 x10¹).",
        inputs=[
            InputField("result_value", "Result", "", True, "text"),
            InputField("result_unit", "Unit", "", False, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_MICRO],
    ),
    "e_coli": LabTest(
        key="e_coli",
        name="E. Coli",
        method="IS 5887 (Part - 1 ) : 1976 RA 2018",
        unit="",
        formula_display="Enter observed result (e.g. Absent).",
        inputs=[
            InputField("result_value", "Result", "", True, "text"),
            InputField("result_unit", "Unit", "", False, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_MICRO],
    ),
    "salmonella": LabTest(
        key="salmonella",
        name="Salmonella",
        method="IS 5887 (Part - 3) : 1999 : RA 2018",
        unit="",
        formula_display="Enter observed result (e.g. Absent).",
        inputs=[
            InputField("result_value", "Result", "", True, "text"),
            InputField("result_unit", "Unit", "", False, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_MICRO],
    ),
    "staphylococcus_aureus": LabTest(
        key="staphylococcus_aureus",
        name="Staphylococcus aureus",
        method="IS 5887 ( Part - 8/Sec-1) :RA 2018",
        unit="",
        formula_display="Enter observed result (e.g. Absent).",
        inputs=[
            InputField("result_value", "Result", "", True, "text"),
            InputField("result_unit", "Unit", "", False, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_MICRO],
    ),
    "yeast_and_mould": LabTest(
        key="yeast_and_mould",
        name="Yeast and Mould",
        method="IS 5403:1999 RA 2018",
        unit="",
        formula_display="Enter observed result (e.g. Absent).",
        inputs=[
            InputField("result_value", "Result", "", True, "text"),
            InputField("result_unit", "Unit", "", False, "text"),
        ],
        calculate=_calc_micro_result,
        categories=[CATEGORY_MICRO],
    ),
}


# Food catalog: 21 unique tests = 11 Jaggery + 10 Basic Nutrition-only keys.
# Basic Nutrition protocol lists 11 rows but shares Appearance with Jaggery
# (22 protocol rows, 21 distinct catalog keys).
FOOD_TEST_KEYS: list[str] = [
    "appearance",
    "moisture",
    "total_ash",
    "acid_insoluble_ash",
    "added_color",
    "extraneous_matter",
    "invert_sugar",
    "reducing_sugar",
    "sucrose",
    "sulphated_ash",
    "sulphur_dioxide",
    "bn_moisture",
    "bn_total_ash",
    "bn_total_fat",
    "bn_protein",
    "bn_carbohydrate",
    "bn_calories",
    "bn_ash_insoluble_hcl",
    "bn_crude_fibre",
    "bn_added_sugar",
    "bn_total_sugar",
]

JAGGERY_TEST_KEYS: list[str] = FOOD_TEST_KEYS[:11]

NUTRITION_TEST_KEYS: list[str] = [
    "appearance",
    "bn_moisture",
    "bn_total_ash",
    "bn_total_fat",
    "bn_protein",
    "bn_carbohydrate",
    "bn_calories",
    "bn_ash_insoluble_hcl",
    "bn_crude_fibre",
    "bn_added_sugar",
    "bn_total_sugar",
]

WATER_TEST_KEYS: list[str] = [
    "ph",
    "tds",
    "chlorides",
    "total_alkalinity",
    "conductivity",
    "total_hardness",
    "calcium_ca",
    "calcium_caco3",
    "magnesium",
    "odor",
    "turbidity",
]

WATER_MICRO_TEST_KEYS: list[str] = [
    "water_total_coliform",
    "water_e_coli",
]

MICRO_TEST_KEYS: list[str] = [
    "total_plate_count",
    "t_coliform",
    "e_coli",
    "salmonella",
    "staphylococcus_aureus",
    "yeast_and_mould",
]


def get_test(key: str) -> LabTest:
    """Return a catalog test by key; built-in first, then active custom formulas."""
    if key in TEST_CATALOG:
        base = TEST_CATALOG[key]
        try:
            from services.catalog_specs import get_spec

            spec = get_spec(key)
        except Exception:  # noqa: BLE001
            spec = None
        if spec is not None:
            return replace(
                base,
                name=spec.test_name or base.name,
                method=spec.method_of_analysis or base.method,
                unit=spec.default_unit if spec.default_unit is not None else base.unit,
            )
        return base
    from services.custom_formulas import load_custom_lab_tests

    custom = load_custom_lab_tests()
    if key in custom:
        return custom[key]
    raise KeyError(key)


def _merged_custom_tests() -> dict[str, LabTest]:
    from services.custom_formulas import load_custom_lab_tests

    return load_custom_lab_tests()


def all_test_keys() -> list[str]:
    """Ordered list of all catalog keys (food, water, micro, plus custom)."""
    custom_keys = [k for k in _merged_custom_tests().keys() if k not in TEST_CATALOG]
    return (
        list(FOOD_TEST_KEYS)
        + list(WATER_TEST_KEYS)
        + list(WATER_MICRO_TEST_KEYS)
        + list(MICRO_TEST_KEYS)
        + custom_keys
    )


def catalog_keys_for_category(category: Optional[str]) -> list[str]:
    """Stable display order for a sample category's catalog tests."""
    cat = normalize_category(category)
    if cat == CATEGORY_WATER:
        base = list(WATER_TEST_KEYS) + list(WATER_MICRO_TEST_KEYS)
    elif cat == CATEGORY_FOOD:
        base = list(FOOD_TEST_KEYS)
    elif cat == CATEGORY_MICRO:
        base = list(MICRO_TEST_KEYS)
    else:
        base = []
    custom_keys = [
        t.key
        for t in _merged_custom_tests().values()
        if cat in (t.categories or []) and t.key not in base
    ]
    return base + custom_keys


def default_test_keys_for_category(category: Optional[str]) -> list[str]:
    """Tests auto-assigned at Reception (water = 13, micro = 6)."""
    cat = normalize_category(category)
    if cat == CATEGORY_WATER:
        return list(WATER_TEST_KEYS) + list(WATER_MICRO_TEST_KEYS)
    if cat == CATEGORY_MICRO:
        return list(MICRO_TEST_KEYS)
    return []


def normalize_category(category: Optional[str]) -> str:
    """Return a valid category key; default food."""
    from services.sample_categories import normalize_sample_category

    return normalize_sample_category(category)


def category_label(category: Optional[str]) -> str:
    """Human-readable label for a category key."""
    from services.sample_categories import all_sample_categories

    key = normalize_category(category)
    return all_sample_categories(include_inactive=True).get(
        key, SAMPLE_CATEGORIES.get(key, SAMPLE_CATEGORIES[CATEGORY_FOOD])
    )


def tests_for_category(category: Optional[str]) -> list[LabTest]:
    """Catalog tests allowed for the given sample category (built-in + custom)."""
    cat = normalize_category(category)
    builtin = [t for t in TEST_CATALOG.values() if cat in (t.categories or [])]
    custom = [
        t for t in _merged_custom_tests().values() if cat in (t.categories or [])
    ]
    return builtin + custom


def list_tests_for_select(category: Optional[str] = None) -> list[tuple[str, str]]:
    """(key, display_label) pairs for Streamlit multiselect, optionally filtered."""
    if category is None:
        tests = list(TEST_CATALOG.values())
    else:
        tests = tests_for_category(category)
    return [(t.key, test_select_label(t)) for t in _ordered_tests(tests, category)]


def test_select_label(test: LabTest) -> str:
    """Multiselect label: test name with optional method reference."""
    method = (test.method or "").strip()
    if method:
        return f"{test.name}  [{method}]"
    return test.name


def _ordered_tests(tests: list[LabTest], category: Optional[str]) -> list[LabTest]:
    """Preserve catalog order when filtering by category; append custom tests."""
    cat = normalize_category(category)
    if cat == CATEGORY_FOOD:
        by_key = {t.key: t for t in tests}
        ordered = [by_key[k] for k in FOOD_TEST_KEYS if k in by_key]
        for t in tests:
            if t.key not in FOOD_TEST_KEYS:
                ordered.append(t)
        return ordered
    if cat == CATEGORY_WATER:
        by_key = {t.key: t for t in tests}
        ordered = [by_key[k] for k in WATER_TEST_KEYS if k in by_key]
        for t in tests:
            if t.key not in WATER_TEST_KEYS:
                ordered.append(t)
        return ordered
    if cat == CATEGORY_MICRO:
        by_key = {t.key: t for t in tests}
        ordered = [by_key[k] for k in MICRO_TEST_KEYS if k in by_key]
        for t in tests:
            if t.key not in MICRO_TEST_KEYS:
                ordered.append(t)
        return ordered
    return tests


def protocol_family_for_key(key: str) -> str:
    """Return jaggery | nutrition for a catalog key."""
    try:
        test = get_test(key)
    except KeyError:
        return PROTOCOL_FAMILY_JAGGERY
    return test.protocol_family


def families_in_keys(keys: list[str]) -> set[str]:
    """Distinct protocol families among selected food test keys."""
    fams: set[str] = set()
    for key in keys:
        try:
            test = get_test(key)
        except KeyError:
            continue
        if CATEGORY_FOOD not in (test.categories or []):
            continue
        fam = test.protocol_family
        if key == "appearance":
            continue
        fams.add(fam)
    return fams


def has_mixed_food_families(keys: list[str]) -> bool:
    """True when both Jaggery and Basic Nutrition tests are selected."""
    fams = families_in_keys(keys)
    return PROTOCOL_FAMILY_JAGGERY in fams and PROTOCOL_FAMILY_NUTRITION in fams


def uses_nutrition_template(keys: list[str]) -> bool:
    """Legacy: infer Basic Nutrition template from selected bn_* keys."""
    return any(k.startswith("bn_") for k in keys)


def test_unsaved_display_name(test_key: str) -> str:
    """Distinct label for generate-time warnings (same name across package groups)."""
    test = TEST_CATALOG.get(test_key)
    if not test:
        return test_key
    method = (test.method or "").strip()
    if method:
        return f"{test.name} [{method}]"
    return test.name


def filter_keys_for_category(keys: list[str], category: Optional[str]) -> list[str]:
    """Keep only catalog keys that belong to the sample category."""
    allowed = {t.key for t in tests_for_category(category)}
    return [k for k in keys if k in allowed]


def missing_required_inputs(test: LabTest, inputs: dict[str, Any]) -> list[str]:
    """Return labels of required fields that are empty."""
    missing = []
    for f in test.inputs:
        if not f.required:
            continue
        val = inputs.get(f.key)
        if val is None or str(val).strip() == "":
            missing.append(f.label)
    if test.key == "bn_protein":
        titrant = protein_titrant_from(inputs)
        norm_key = protein_normality_key(titrant)
        norm_label = protein_normality_label(titrant)
        if not str(inputs.get(norm_key) or "").strip():
            missing.append(f"Normality of {norm_label}")
    return missing


def excess_decimal_inputs(test: LabTest, inputs: dict[str, Any]) -> list[str]:
    """Return labels of number fields with more than 4 decimal places."""
    from services.number_format import validate_max_decimals

    labels: list[str] = []
    for f in test.inputs:
        if f.field_type != "number":
            continue
        val = inputs.get(f.key)
        if val is None or str(val).strip() == "":
            continue
        try:
            validate_max_decimals(str(val), 4)
        except ValueError:
            labels.append(f.label)
    return labels
