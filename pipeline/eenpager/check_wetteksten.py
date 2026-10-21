"""Check that the law texts quoted on /voorstel/ still match the law in force.

Downloads the current version of the Grondwet, Gemeentewet and Wet WOZ from the
official BWB repository (the source of wetten.overheid.nl) and compares every
<figure class="wetcitaat" data-bron="BWBR...:artikel"> quote in
content/voorstel/_index.md, plus a few short inline quotes, word for word.

Usage (from the repository root):
    python3 -I pipeline/eenpager/check_wetteksten.py [YYYY-MM-DD]
"""

import datetime
import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

REPO = "https://repository.officiele-overheidspublicaties.nl/bwb"
PAGE = "content/voorstel/_index.md"
WETTEN = {"BWBR0001840": "Grondwet", "BWBR0005416": "Gemeentewet", "BWBR0007119": "Wet WOZ"}

# Short quotes used inline (in the table and in the draft's amendment instructions).
INLINE = [
    ("BWBR0001840", "132", "De wet bepaalt welke belastingen door de besturen van provincies en gemeenten kunnen worden geheven en regelt hun financiële verhouding tot het Rijk."),
    ("BWBR0005416", "220f", "Het percentage wordt gelijkelijk vastgesteld voor onderscheidenlijk"),
    ("BWBR0007119", "17", "Aan een onroerende zaak wordt een waarde toegekend."),
    ("BWBR0007119", "20", "bepaalt de waarde van die onroerende zaak"),
    ("BWBR0007119", "23", "het kalenderjaar waarvoor de beschikking geldt."),
]


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def current_version(bwb, day):
    work = ET.fromstring(fetch(f"{REPO}/{bwb}/manifest.xml"))
    for e in work.findall("expression"):
        m = e.find("metadata")
        start, end = m.findtext("datum_inwerkingtreding"), m.findtext("einddatum") or "9999-12-31"
        if start <= day <= end:
            label = e.get("label")
            return label, ET.fromstring(fetch(f"{REPO}/{bwb}/{label}/xml/{bwb}_{label}.xml"))
    sys.exit(f"geen geldende versie van {bwb} op {day}")


def norm(s):
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def flat(el):
    parts = []

    def rec(e):
        if e.tag in ("meta-data", "redactie", "noot"):
            parts.append(e.tail or "")
            return
        parts.append(e.text or "")
        for c in e:
            rec(c)
        parts.append(e.tail or "")

    rec(el)
    return norm("".join(parts))


def paragraphs(root, nr):
    """All <al> texts (leden and list items) of one article."""
    for a in root.iter("artikel"):
        kop = a.find("kop")
        if kop is not None and (kop.findtext("nr") or "").strip() == nr:
            return [flat(al) for al in a.iter("al")]
    sys.exit(f"artikel {nr} niet gevonden")


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    laws = {}
    for bwb, naam in WETTEN.items():
        label, root = current_version(bwb, day)
        laws[bwb] = root
        print(f"{naam}: versie {label}")

    page = open(PAGE, encoding="utf-8").read()
    ok, n = True, 0
    for m in re.finditer(r'<figure class="wetcitaat" data-bron="(\w+):(\w+)">(.*?)</figure>', page, re.S):
        bwb, nr, body = m.groups()
        units = paragraphs(laws[bwb], nr)
        quote = re.search(r"<blockquote>(.*?)</blockquote>", body, re.S).group(1)
        for p in re.findall(r"<p[^>]*>(.*?)</p>", quote, re.S):
            text = re.sub(r"^(\d+|[a-z])\. ", "", norm(re.sub(r"<[^>]+>", "", p)))
            n += 1
            if text not in units:
                ok = False
                print(f"AFWIJKING {WETTEN[bwb]} art. {nr}: {text[:80]}")
    for bwb, nr, text in INLINE:
        n += 1
        if not any(text in u for u in paragraphs(laws[bwb], nr)):
            ok = False
            print(f"AFWIJKING {WETTEN[bwb]} art. {nr}: {text[:80]}")
    print(f"{n} citaten gecontroleerd: {'alles klopt' if ok else 'pas de pagina aan'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
