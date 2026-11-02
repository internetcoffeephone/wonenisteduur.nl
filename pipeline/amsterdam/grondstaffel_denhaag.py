# /// script
# requires-python = ">=3.11"
# dependencies = ["pypdf>=4.0", "requests>=2.31"]
# ///
"""Download Den Haag's published grondstaffels and extract them to input/grondstaffel/denhaag/.

Den Haag publishes a "Bijlage Grondstaffels" with its Verantwoordingsdocument
WOZ every year (https://www.denhaag.nl/nl/belastingen/woz-waarde-en-taxatieverslag.htm):
a land price per m2 of kavel per buurt and woningtype, in bands of kavel m2.

    uv run grondstaffel_denhaag.py

  2024 = belastingjaar 2024, waardepeildatum 1-1-2023, buurt codes
  2025 = belastingjaar 2025, waardepeildatum 1-1-2024, buurt names (same
         peildatum as the CBS WOZ averages used in 03_land.py)
  2026 = belastingjaar 2026, waardepeildatum 1-1-2025, buurt codes

A row holds 7 prices (type A, vrijstaand) or 8 (the other types); the column
headers give the band of kavel m2 each price starts at. 08_denhaag.py reads a
price as applying to the m2 within its band, as Amsterdam's staffel does; the
document itself only says that larger kavels get a lower price per m2.

The 2025 tables name the buurten. The 2026 Bijlage Bijgebouwen lists the
gemeente's code next to each name. Code W02071 is wijk 02, buurt 071, which is
CBS buurt BU0518 + 02 + 71; 08_denhaag.py checks this against the CBS names.
The 2026 tables also hold rows by name, for buurten that already have rows by
code; those named rows repeat the 2025 prices and are dropped.

Writes (committed): input/grondstaffel/denhaag/grondstaffel.csv, one row per
belastingjaar, buurt, woningtype and band.

The PDFs are only parsed as text, never executed.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from pypdf import PdfReader

from common import CACHE_ROOT, HERE, log, session

RAW = CACHE_ROOT / "denhaag" / "raw" / "grondstaffel"
DEST = HERE / "input" / "grondstaffel" / "denhaag"
BASE = "https://www.denhaag.nl/wp-content/uploads/2022/02/"
STAFFELS = {  # belastingjaar: (waardepeildatum, file)
    2024: ("2023-01-01", "Bijlage-Grondstaffels-Gemeente-Den-Haag-2024.pdf"),
    2025: ("2024-01-01", "Bijlage-Grondstaffels-2025.pdf"),
    2026: ("2025-01-01", "Grondstaffels-2026.pdf"),
}
CODES = "Bijgebouwen-2026.pdf"  # code next to name for every buurt

# Lower bound of each price's band, by number of prices in the row. All bands
# in the headers: 0, 100, 150, 250, 300, 350, 450, 500, 1000, 2000, 2500, 5000.
BANDS = {7: (0, 150, 300, 500, 1000, 2000, 2500), 8: (0, 100, 150, 250, 350, 450, 1000, 2000)}
TYPES = {"A", "B", "BG", "C", "D", "E", "E1", "E2", "F", "G", "H", "I", "J", "K", "X", "Z"}
SPECIAL = {"INC", "WIN"}  # single rows outside the buurt tables, not used
ROW = re.compile(r"^(?:20\d\d )?2030 (?:T O )?(.*?)\s*\b([A-Z]{1,3}\d?) ((?:\d+ ?)+)$")
CODE = re.compile(r"^W\d{5}$")


def fetch(name: str) -> Path:
    f = RAW / name
    if not f.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        r = session().get(BASE + name, timeout=120)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            raise SystemExit(f"{name}: not a PDF")
        tmp = f.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(f)
        log("downloaded", name, len(r.content), "bytes")
    return f


def lines(pdf: Path) -> list[str]:
    return [ln.strip() for page in PdfReader(str(pdf)).pages for ln in (page.extract_text() or "").splitlines()]


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def code_names() -> dict[str, str]:
    """Gemeente buurt code per normalised buurt name, from the 2026 Bijlage Bijgebouwen."""
    names = {}
    for ln in lines(fetch(CODES)):
        m = re.search(r"\b(W\d{5})\s+(.+?)\s{2,}", ln)
        if m:
            names.setdefault(norm(m.group(2)), set()).add(m.group(1))
    if any(len(c) > 1 for c in names.values()) or len(names) < 100:
        raise SystemExit(f"{CODES}: unexpected code list ({len(names)} names)")
    return {n: c.pop() for n, c in names.items()}


def staffel(jaar: int) -> list[dict]:
    """Rows of one Bijlage Grondstaffels: gebied (code or name), type and prices."""
    rows, special = [], 0
    for ln in lines(fetch(STAFFELS[jaar][1])):
        m = ROW.match(ln)
        if not m:
            continue
        gebied, typ, prices = m.group(1).strip(), m.group(2), [int(p) for p in m.group(3).split()]
        if typ in SPECIAL:
            special += 1
            continue
        if typ not in TYPES or len(prices) not in BANDS or not gebied:
            raise SystemExit(f"{jaar}: unexpected row {ln!r}")
        rows.append({"gebied": gebied, "type": typ, "prices": prices})
    log(jaar, len(rows), "rows,", special, "special rows skipped")
    if len(rows) < 1300:
        raise SystemExit(f"{jaar}: expected about 1,470 rows, found {len(rows)}")
    return rows


def main() -> None:
    codes = code_names()
    tables = {jaar: staffel(jaar) for jaar in STAFFELS}
    by_name_2025 = {(r["gebied"], r["type"]): r["prices"] for r in tables[2025]}
    out = []
    for jaar, rows in tables.items():
        coded = {r["gebied"] for r in rows if CODE.match(r["gebied"])}
        dropped = same = 0
        for r in rows:
            named = not CODE.match(r["gebied"])
            code = codes.get(norm(r["gebied"])) if named else r["gebied"]
            if code is None:
                raise SystemExit(f"{jaar}: no code for buurt {r['gebied']!r}")
            if named and jaar != 2025 and code in coded:
                dropped += 1
                same += by_name_2025.get((r["gebied"], r["type"])) == r["prices"]
                continue
            for van, p in zip(BANDS[len(r["prices"])], r["prices"]):
                out.append({"belastingjaar": jaar, "peildatum": STAFFELS[jaar][0], "woz_code": code,
                            "buurtcode": "BU0518" + code[1:3] + code[4:6], "type": r["type"],
                            "van_m2": van, "prijs_m2": p})
        if dropped:
            log(jaar, dropped, "rows by name dropped (buurt also has rows by code),", same, "identical to 2025")
    pairs = {(r["woz_code"], r["buurtcode"]) for r in out}
    if len({b for _, b in pairs}) != len(pairs):
        raise SystemExit("two gemeente codes give the same CBS buurtcode")
    DEST.mkdir(parents=True, exist_ok=True)
    with open(DEST / "grondstaffel.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    log("grondstaffel.csv:", len(out), "rows")


if __name__ == "__main__":
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings; the text is complete without fontTools
    main()
