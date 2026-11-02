# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=4.0"]
# ///
"""Extract Amsterdam's published grondstaffel tables into input/grondstaffel/*.csv.

The gemeente publishes a Verantwoordingsdocument WOZ every year at
https://www.amsterdam.nl/belastingen/verantwoordingsdocument-woz, with the
grondstaffel (land price per m2 of kavel for grondgebonden woningen) as an
annex. amsterdam.nl blocks scripted downloads, so download the PDFs in a
browser and pass their paths:

    uv run grondstaffel_pdf.py --vd2024 "Verantwoordingsdocument WOZ 2024.pdf" \\
                               --vd2025 "Verantwoordingsdocument WOZ 2025.pdf"

  vd2024 = belastingjaar 2024, waardepeildatum 1-1-2023
  vd2025 = belastingjaar 2025, waardepeildatum 1-1-2024 (same peildatum as the
           CBS WOZ averages used in 03_land.py)

Writes (committed, small):
  input/grondstaffel/basisprijs.csv          base price per m2 per objecttype and area
  input/grondstaffel/staffel.csv             marginal factor per band of kavel m2
  input/grondstaffel/buurtcorrectie_egw.csv  correction per buurt, eengezinswoningen (vd2025)

The PDFs are only parsed as text, never executed. Every table is checked
against the row counts printed in the document; a mismatch stops the script.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
DEST = HERE / "input" / "grondstaffel"

WAARDEGEBIEDEN = ("Centrum", "Nieuw-West/Westpoort", "Noord", "Oost", "Weesp", "West", "Zuid", "Zuidoost")
TYPES = ("rij_hoek", "twee_onder_een_kap", "vrijstaand")
WG = "|".join(re.escape(w) for w in WAARDEGEBIEDEN)


def lines(pdf: Path) -> list[str]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)
    return [ln.strip() for ln in text.splitlines()]


def annex(ls: list[str], title: str) -> list[str]:
    """Lines from the last occurrence of an annex title (the first is the table of contents)."""
    starts = [i for i, ln in enumerate(ls) if ln.startswith(title)]
    if not starts:
        raise SystemExit(f"annex not found: {title!r}")
    return ls[starts[-1]:]


def num(s: str) -> float:
    """Dutch (1.234,56) or English (1,234.56) notation."""
    s = s.replace("€", "").strip()
    if re.fullmatch(r"[\d.]*,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    return float(s.replace(",", ""))


STAFFEL = re.compile(r"^(\d+)\s*(?:-\s*(\d+)?|\+)\s+(-?\d+(?:,\d+)?)\s+(\d+)%")  # "101 - 200", "1601-", "1001+"


def staffels(ls: list[str], peildatum: str, types: tuple[str, ...], stop: str) -> list[dict]:
    """Staffel blocks in document order; one block per objecttype."""
    rows, block = [], -1
    for ln in ls:
        if ln.startswith(stop):
            break
        if ln.startswith("STAFFELLAAG"):
            block += 1
            continue
        m = STAFFEL.match(ln)
        if m and 0 <= block < len(types):
            rows.append({"peildatum": peildatum, "objecttype": types[block], "van_m2": int(m.group(1)),
                         "tot_m2": m.group(2) or "", "factor": int(m.group(4)) / 100})
    return rows


def vd2025(ls: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    peil = "2024-01-01"
    gs = annex(ls, "Bijlage 2: Grondstaffel")
    st = staffels(gs, peil, TYPES, "Bijlage 3")
    price = re.compile(rf"\b({WG}) € ([\d,]+\.\d+)$")
    prices = []
    for ln in gs:
        if ln.startswith("Bijlage 3"):
            break
        m = price.search(ln)
        if m:
            prices.append((m.group(1), num(m.group(2))))
    if len(prices) != len(TYPES) * len(WAARDEGEBIEDEN):
        raise SystemExit(f"vd2025: expected 24 base prices, found {len(prices)}")
    bp = [{"peildatum": peil, "objecttype": TYPES[i // 8], "gebied": wg, "gebiedssoort": "waardegebied",
           "segment": "", "basisprijs_m2": p} for i, (wg, p) in enumerate(prices)]
    corr = re.compile(rf"^({WG}) (\S+) (.+?) (-?\d+\.\d+)%$")
    bc = []
    for ln in annex(ls, "Bijlage 5: Buurtgroepcorrecties Eengezinswoningen"):
        m = corr.match(ln)
        if m:
            bc.append({"peildatum": peil, "buurtcode": "BU0363" + m.group(2), "buurtnaam": m.group(3),
                       "waardegebied": m.group(1), "correctie": float(m.group(4)) / 100})
    if len(bc) < 500 or len({r["buurtcode"] for r in bc}) != len(bc):
        raise SystemExit(f"vd2025: unexpected buurt corrections ({len(bc)})")
    return bp, st, bc


def vd2024(ls: list[str]) -> tuple[list[dict], list[dict]]:
    """Rij- en hoekwoningen only (BASISSOC 1431): segment base price for its basisbuurt."""
    peil = "2023-01-01"
    gs = annex(ls, "Bijlage 2: Grondstaffel")
    st = staffels(gs, peil, ("rij_hoek", "vrijstaand_twee"), "Bijlage 3")
    seg = re.compile(r"^(\d+) Rij en hoek, (.+?) (\d+(?:,\d+)?) 1431 (.+)$")
    bp = []
    for ln in gs:
        if ln.startswith("Bijlage 3"):
            break
        m = seg.match(ln)
        if m:
            bp.append({"peildatum": peil, "objecttype": "rij_hoek", "gebied": m.group(4), "gebiedssoort": "basisbuurt",
                       "segment": f"{m.group(1)} {m.group(2)}", "basisprijs_m2": num(m.group(3))})
    if len(bp) < 25:
        raise SystemExit(f"vd2024: expected at least 25 rij/hoek segments, found {len(bp)}")
    return bp, st


def write(name: str, rows: list[dict]) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    with open(DEST / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vd2024", type=Path, required=True)
    ap.add_argument("--vd2025", type=Path, required=True)
    a = ap.parse_args()
    bp25, st25, bc25 = vd2025(lines(a.vd2025))
    bp24, st24 = vd2024(lines(a.vd2024))
    write("basisprijs.csv", bp24 + bp25)
    write("staffel.csv", st24 + st25)
    write("buurtcorrectie_egw.csv", bc25)


if __name__ == "__main__":
    main()
