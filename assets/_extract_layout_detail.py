"""Layout geometry details for Test Report Format PDF."""
from pathlib import Path

import pdfplumber

PDF = Path(r"g:\Monika\S_LAB\reference\Test Report Format (1).pdf")
OUT = Path(r"g:\Monika\S_LAB\assets\_test_report_layout.txt")


def main() -> None:
    lines: list[str] = []
    with pdfplumber.open(PDF) as pdf:
        for i, page in enumerate(pdf.pages):
            lines.append(f"==== PAGE {i + 1} ====")
            top_chars = [c for c in (page.chars or []) if c["top"] < 130]
            lines.append(f"top margin chars (<130): {len(top_chars)}")
            if top_chars:
                t = "".join(
                    c["text"]
                    for c in sorted(top_chars, key=lambda c: (c["top"], c["x0"]))
                )
                lines.append(f"  text: {t!r}")

            top_rects = [r for r in (page.rects or []) if r["top"] < 160]
            lines.append(f"top rects: {len(top_rects)}")
            for r in sorted(top_rects, key=lambda r: (r["top"], r["x0"]))[:20]:
                lines.append(
                    f"  rect y={r['top']:.1f}-{r['bottom']:.1f} "
                    f"x={r['x0']:.1f}-{r['x1']:.1f} "
                    f"w={r['width']:.1f} h={r['height']:.1f}"
                )

            for ti, t in enumerate(page.find_tables()):
                lines.append(f"TABLE {ti} bbox={t.bbox}")
                if t.cells:
                    cells = [c for c in t.cells if c]
                    xs = sorted(
                        {round(c[0], 1) for c in cells}
                        | {round(c[2], 1) for c in cells}
                    )
                    ys = sorted(
                        {round(c[1], 1) for c in cells}
                        | {round(c[3], 1) for c in cells}
                    )
                    lines.append(f"  x_edges={xs}")
                    lines.append(f"  y_edges={ys}")
                    lines.append(f"  n_cells={len(cells)}")

            # Signature band approximate Y
            sig = [
                c
                for c in (page.chars or [])
                if "Surendra" in "".join(
                    x["text"]
                    for x in (page.chars or [])
                    if abs(x["top"] - c["top"]) < 2
                )
            ]
            lines.append(
                f"page height={page.height}, content approx left~60 right~535"
            )

            # Empty Result column note - check blank cells in results
            tables = page.find_tables()
            if len(tables) >= 3:
                data = tables[2].extract()
                for ri, row in enumerate(data or []):
                    if ri == 0:
                        continue
                    result = (row[2] or "").strip() if len(row) > 2 else ""
                    name = (row[1] or "").strip()[:40] if len(row) > 1 else ""
                    lines.append(f"  result_blank row{ri} '{name}': {result!r}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
