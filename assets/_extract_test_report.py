"""One-off extractor for Test Report Format PDF structure."""
from __future__ import annotations

from pathlib import Path

import pdfplumber
from pypdf import PdfReader

PDF = Path(r"g:\Monika\S_LAB\reference\Test Report Format (1).pdf")
OUT = Path(r"g:\Monika\S_LAB\assets\_test_report_extract.txt")


def clean(s: str) -> str:
    return (
        (s or "")
        .replace("\uf0b7", "•")
        .replace("\u2022", "•")
        .replace("\n", " / ")
        .strip()
    )


def main() -> None:
    lines: list[str] = []

    reader = PdfReader(str(PDF))
    lines.append(f"PAGES: {len(reader.pages)}")
    lines.append(f"PDF metadata: {reader.metadata}")
    for i, p in enumerate(reader.pages):
        res = p.get("/Resources") or {}
        xobj = res.get("/XObject")
        lines.append(f"--- pypdf page {i+1} ---")
        if xobj:
            xobj = xobj.get_object() if hasattr(xobj, "get_object") else xobj
            lines.append(f"XObjects: {list(xobj.keys())}")
            for name, obj in xobj.items():
                o = obj.get_object() if hasattr(obj, "get_object") else obj
                lines.append(
                    f"  {name}: subtype={o.get('/Subtype')}, "
                    f"w={o.get('/Width')}, h={o.get('/Height')}, "
                    f"filter={o.get('/Filter')}, cs={o.get('/ColorSpace')}"
                )
        else:
            lines.append("XObjects: none")
        annots = p.get("/Annots")
        lines.append(f"annots: {len(annots) if annots else 0}")

    with pdfplumber.open(PDF) as pdf:
        lines.append(f"pdfplumber pages: {len(pdf.pages)}")
        lines.append(f"pdfplumber metadata: {pdf.metadata}")
        for i, page in enumerate(pdf.pages):
            lines.append("=" * 80)
            lines.append(f"PAGE {i + 1}")
            lines.append(f"size: {page.width} x {page.height}")
            lines.append(f"chars: {len(page.chars or [])}")
            lines.append(f"images count: {len(page.images or [])}")
            for im in page.images or []:
                lines.append(f"  image: {im}")
            lines.append(f"rects: {len(page.rects or [])}")
            lines.append(f"curves: {len(page.curves or [])}")
            lines.append(f"lines: {len(page.lines or [])}")

            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            text = text.replace("\uf0b7", "•").replace("\u2022", "•")
            lines.append("---FULL TEXT---")
            lines.append(text)
            lines.append("---END FULL TEXT---")

            words = page.extract_words(x_tolerance=2, y_tolerance=3) or []
            lines.append(f"---WORDS ({len(words)}) by Y---")
            rows: dict[int, list] = {}
            for w in words:
                y = round(w["top"] / 3) * 3
                rows.setdefault(y, []).append(w)
            for y in sorted(rows.keys()):
                row_words = sorted(rows[y], key=lambda w: w["x0"])
                parts = [f"{w['text']}@{int(w['x0'])}" for w in row_words]
                lines.append(f"Y{y}: " + " | ".join(parts))

            tables = page.find_tables()
            lines.append(f"---TABLES ({len(tables)})---")
            for ti, t in enumerate(tables):
                lines.append(f"=== TABLE {ti} bbox={t.bbox} ===")
                data = t.extract()
                if not data:
                    continue
                for ri, row in enumerate(data):
                    cells = [clean(c) for c in row]
                    lines.append(f"R{ri}| " + " || ".join(cells))

            # Character font sampling for header detection
            fonts = {}
            for c in page.chars or []:
                key = (c.get("fontname"), round(c.get("size", 0), 1))
                fonts[key] = fonts.get(key, 0) + 1
            lines.append("---FONTS (count)---")
            for (fn, sz), cnt in sorted(fonts.items(), key=lambda x: -x[1])[:20]:
                lines.append(f"  {fn} {sz}pt: {cnt}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
