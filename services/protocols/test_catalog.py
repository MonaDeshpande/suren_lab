"""
services/protocols/test_catalog.py
----------------------------------
SHARED library of lab tests + formulas, tagged by sample category.

Reception picks Food / Water / Cattle Feed–Fertilizer; only matching tests
are offered. Selecting "Moisture" always uses the SAME inputs and formula.

Current catalog: 11 Food tests. Add more LabTest entries (Food 12–25, Water,
Feed) with categories=[...] — Reception filtering picks them up automatically.
Protocol Word templates for non-Food categories can be added later.

Source of names/methods/worksheet fields (Food):
  reference/Jaggery Protocol LLP.docx (layout reference only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Stable category keys stored on request_samples.category
CATEGORY_FOOD = "food"
CATEGORY_WATER = "water"
CATEGORY_CATTLE_FEED_FERTILIZER = "cattle_feed_fertilizer"

SAMPLE_CATEGORIES: dict[str, str] = {
    CATEGORY_FOOD: "Food",
    CATEGORY_WATER: "Water",
    CATEGORY_CATTLE_FEED_FERTILIZER: "Cattle Feed / Fertilizer",
}

VALID_CATEGORIES = frozenset(SAMPLE_CATEGORIES.keys())


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
    """

    key: str
    name: str
    method: str
    unit: str
    formula_display: str
    inputs: list[InputField]
    calculate: Callable[[dict[str, Any], dict[str, float]], tuple[str, Optional[float]]]
    categories: list[str] = field(default_factory=lambda: [CATEGORY_FOOD])

def _f(inputs: dict[str, Any], key: str) -> float:
    """Parse a required numeric input; raises ValueError if missing/invalid."""
    raw = inputs.get(key)
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"Missing value: {key}")
    return float(raw)


def _round(n: float, places: int = 2) -> float:
    return round(n, places)


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
    moisture = ctx.get("moisture")
    if moisture is None:
        # Allow override from worksheet if moisture not yet saved
        if str(inputs.get("moisture_pct") or "").strip():
            moisture = _f(inputs, "moisture_pct")
        else:
            raise ValueError(
                "Moisture result is required for dry-basis ash "
                "(save Moisture first, or enter moisture_pct)"
            )
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
    moisture = ctx.get("moisture")
    if moisture is None and str(inputs.get("moisture_pct") or "").strip():
        moisture = _f(inputs, "moisture_pct")
    if moisture is None:
        raise ValueError("Moisture result required for dry-basis (save Moisture first)")
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
    moisture = ctx.get("moisture")
    if moisture is None and str(inputs.get("moisture_pct") or "").strip():
        moisture = _f(inputs, "moisture_pct")
    if moisture is None:
        raise ValueError("Moisture result required for dry-basis")
    dry = _round(ext * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _sugar_percent(concentration: float, sample_wt: float, br: float) -> float:
    # Concentration(g) * 250 * 100 / (Wt * B.R.)
    if sample_wt == 0 or br == 0:
        raise ValueError("Sample weight and B.R. must be non-zero")
    return concentration * 250.0 * 100.0 / (sample_wt * br)


def _calc_invert_sugar(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    conc = _f(inputs, "sugar_conc")
    w = _f(inputs, "sample_wt")
    br = _f(inputs, "br_invert")
    wet = _sugar_percent(conc, w, br)
    moisture = ctx.get("moisture")
    if moisture is None and str(inputs.get("moisture_pct") or "").strip():
        moisture = _f(inputs, "moisture_pct")
    if moisture is None:
        raise ValueError("Moisture result required for dry-basis sugar")
    dry = _round(wet * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_reducing_sugar(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    conc = _f(inputs, "sugar_conc")
    w = _f(inputs, "sample_wt")
    br = _f(inputs, "br_reducing")
    wet = _sugar_percent(conc, w, br)
    moisture = ctx.get("moisture")
    if moisture is None and str(inputs.get("moisture_pct") or "").strip():
        moisture = _f(inputs, "moisture_pct")
    if moisture is None:
        raise ValueError("Moisture result required for dry-basis sugar")
    dry = _round(wet * 100.0 / (100.0 - moisture))
    return f"{dry}", dry


def _calc_sucrose(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    # Sucrose (dry) ≈ Invert sugar (dry) - Reducing sugar (dry)
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
    sucrose = _round(inv - red)
    return f"{sucrose}", sucrose


def _calc_sulphated_ash(inputs: dict, ctx: dict) -> tuple[str, Optional[float]]:
    w1 = _f(inputs, "w1")
    w2 = _f(inputs, "w2")
    w = _f(inputs, "w")
    if w == 0:
        raise ValueError("Sample weight W cannot be zero")
    ash = (w2 - w1) * 100.0 / w
    moisture = ctx.get("moisture")
    if moisture is None and str(inputs.get("moisture_pct") or "").strip():
        moisture = _f(inputs, "moisture_pct")
    if moisture is None:
        raise ValueError("Moisture result required for dry-basis")
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
        formula_display="Ash % = (W2-W1)×100/W ; Dry basis = Ash×100/(100-moisture)",
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Sample before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Sample after ignition", "g", False),
            InputField("w2", "Weight of dish + Sample after ignition (W2)", "g"),
            InputField("moisture_pct", "Moisture % (if not already saved)", "%", False),
        ],
        calculate=_calc_total_ash,
    ),
    "acid_insoluble_ash": LabTest(
        key="acid_insoluble_ash",
        name="Ash Insoluble in dilute HCL on dry basis",
        method="IS 12923:1990",
        unit="%",
        formula_display="Insoluble ash % = (W2-W1)×100/W ; Dry basis = ×100/(100-moisture)",
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Insoluble ash before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Insoluble ash after ignition", "g", False),
            InputField("w2", "Weight of dish + Insoluble ash after ignition (W2)", "g"),
            InputField("moisture_pct", "Moisture % (if not already saved)", "%", False),
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
        formula_display="Extraneous % = (W1-W2)×100/W ; Dry basis = ×100/(100-moisture)",
        inputs=[
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("w2_filter", "Weight of Filter Paper (W2)", "g"),
            InputField("w1_matter", "Weight of Filter Paper + Dry Extraneous matter (W1)", "g"),
            InputField("moisture_pct", "Moisture % (if not already saved)", "%", False),
        ],
        calculate=_calc_extraneous,
    ),
    "invert_sugar": LabTest(
        key="invert_sugar",
        name="Total sugar expressed as Invert sugar on dry weight basis",
        method="IS:15279 : 2003",
        unit="%",
        formula_display="Invert % = Conc(g)×250×100 / (Wt × B.R.) ; then dry basis with moisture",
        inputs=[
            InputField("sample_wt", "Amount of sample taken (gms)", "g"),
            InputField("fehling_invert", "Fehling solution for Total Invert sugar", "ml", False),
            InputField("br_invert", "B.R. reading for invert sugar", "ml"),
            InputField("sugar_conc", "Concentration of sugar (g)", "g"),
            InputField("moisture_pct", "Moisture % (if not already saved)", "%", False),
        ],
        calculate=_calc_invert_sugar,
    ),
    "reducing_sugar": LabTest(
        key="reducing_sugar",
        name="Total sugar expressed as Reduced sugar (on dry basis)",
        method="IS:15279 : 2003",
        unit="%",
        formula_display="Reducing % = Conc(g)×250×100 / (Wt × B.R.) ; then dry basis with moisture",
        inputs=[
            InputField("sample_wt", "Amount of sample taken (gms)", "g"),
            InputField("fehling_reducing", "Fehling solution for Reducing sugar", "ml", False),
            InputField("br_reducing", "B.R. reading for reducing sugar", "ml"),
            InputField("sugar_conc", "Concentration of sugar (g)", "g"),
            InputField("moisture_pct", "Moisture % (if not already saved)", "%", False),
        ],
        calculate=_calc_reducing_sugar,
    ),
    "sucrose": LabTest(
        key="sucrose",
        name="Sucrose % on dry basis",
        method="IS:15279 : 2018",
        unit="%",
        formula_display="Sucrose (dry) % = Invert sugar (dry) - Reducing sugar (dry)",
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
        formula_display="Sulphated ash % = (W2-W1)×100/W ; Dry basis = ×100/(100-moisture)",
        inputs=[
            InputField("w1", "Weight of empty Crucible (W1)", "g"),
            InputField("before_ign", "Weight of Crucible + Sample before ignition", "g", False),
            InputField("w", "Weight of sample taken (W)", "g"),
            InputField("after_ign", "Weight of Crucible + Sample after ignition", "g", False),
            InputField("w2", "Weight of dish + Sample after ignition (W2)", "g"),
            InputField("moisture_pct", "Moisture % (if not already saved)", "%", False),
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
}


def get_test(key: str) -> LabTest:
    """Return a catalog test by key; raises KeyError if unknown."""
    return TEST_CATALOG[key]


def all_test_keys() -> list[str]:
    """Ordered list of all catalog keys."""
    return list(TEST_CATALOG.keys())


def normalize_category(category: Optional[str]) -> str:
    """Return a valid category key; default food."""
    key = (category or "").strip().lower()
    if key in VALID_CATEGORIES:
        return key
    return CATEGORY_FOOD


def category_label(category: Optional[str]) -> str:
    """Human-readable label for a category key."""
    return SAMPLE_CATEGORIES.get(normalize_category(category), SAMPLE_CATEGORIES[CATEGORY_FOOD])


def tests_for_category(category: Optional[str]) -> list[LabTest]:
    """Catalog tests allowed for the given sample category."""
    cat = normalize_category(category)
    return [t for t in TEST_CATALOG.values() if cat in (t.categories or [])]


def list_tests_for_select(category: Optional[str] = None) -> list[tuple[str, str]]:
    """(key, display_label) pairs for Streamlit multiselect, optionally filtered."""
    if category is None:
        tests = list(TEST_CATALOG.values())
    else:
        tests = tests_for_category(category)
    return [(t.key, f"{t.name}  [{t.method}]") for t in tests]


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
    return missing
