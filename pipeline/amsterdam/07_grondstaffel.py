# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "numpy>=1.26"]
# ///
"""Check: compare our land prices with the municipality's published grondstaffel.

    uv run 07_grondstaffel.py      (after 06_publish.py, which rewrites the site JSON)

Amsterdam's WOZ model splits the value of a grondgebonden woning into a woning
part and a grond part. The grond part is a price per m2 of kavel per objecttype
and waardegebied, with a staffel for larger kavels and a correction per buurt
(input/grondstaffel/, from grondstaffel_pdf.py). Apartments get no grond part.

For buurten where most dwellings are grondgebonden, the official land value of
a kavel of the buurt's mean land per dwelling is compared with our estimate:

    official value = basisprijs(waardegebied) x (1 + buurtcorrectie) x staffel(kavel m2)

Also checks how stable the official split is: the same basisbuurten at two
peildata (first 100 m2, where both staffels count 100%).

Reads only committed files (output/, input/grondstaffel/), no cache. Writes
  output/vergelijking_grondstaffel.csv     per buurt
  output/samenvatting_grondstaffel.json    aggregates
  data/amsterdam/cijfers.json              gs_* keys added
  data/amsterdam/tabellen.json             "grondstaffel" rows added
  static/amsterdam/data/vergelijking_grondstaffel.csv
"""

from __future__ import annotations

import re
import shutil

import pandas as pd

from common import (HERE, OUT, SITE_DATA, SITE_STATIC, amsterdam_only, eur, log, nl, params, pct, read_json,
                    staffel_waarde, write_json)

P = params()
G = P["grondstaffel"]
IN = HERE / "input" / "grondstaffel"
MAAND = ("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
         "november", "december")


def datum(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MAAND[m - 1]} {y}"


def norm(name: str) -> str:
    return re.sub(r"[\s-]+", " ", name.lower()).strip()


def main():
    peil, vorig, typ = G["peildatum"], G["vorige_peildatum"], G["objecttype"]
    bp = pd.read_csv(IN / "basisprijs.csv")
    st = pd.read_csv(IN / "staffel.csv")
    bc = pd.read_csv(IN / "buurtcorrectie_egw.csv").set_index("buurtcode")
    ours = pd.read_csv(OUT / "buurt_grondprijs.csv")
    sl = read_json(OUT / "samenvatting_grond.json")

    prijs = bp[(bp.peildatum == peil) & (bp.objecttype == typ)].set_index("gebied").basisprijs_m2
    bands = st[(st.peildatum == peil) & (st.objecttype == typ)].sort_values("van_m2")
    van, factor = [0, *bands.tot_m2.dropna()], list(bands.factor)  # "0-100", "101-200": edges at 100, 200

    # ------------------------------------------------------------ per buurt
    b = ours[(ours.bron_grondprijs == "buurt") & (ours.pct_grondgebonden_bag >= G["min_pct_grondgebonden"])
             & ours.buurtcode.isin(bc.index)].copy()
    b = b.join(bc[["waardegebied", "correctie"]], on="buurtcode")
    b["basisprijs_m2"] = b.waardegebied.map(prijs)
    b["kavel_m2"] = b.grond_m2_per_woning
    b["grondwaarde_gemeente"] = b.basisprijs_m2 * (1 + b.correctie) * b.kavel_m2.map(lambda a: staffel_waarde(a, van, factor))
    b["grondprijs_m2_gemeente"] = b.grondwaarde_gemeente / b.kavel_m2
    b["grondaandeel_gemeente"] = b.grondwaarde_gemeente / b.woz_gem
    b["verhouding"] = b.grondprijs_m2_central / b.grondprijs_m2_gemeente
    b["binnen_band"] = b.grondprijs_m2_gemeente.between(b.grondprijs_m2_low, b.grondprijs_m2_high)
    cols = ["buurtcode", "buurtnaam", "waardegebied", "woningen_bag", "pct_grondgebonden_bag", "woz_gem", "kavel_m2",
            "basisprijs_m2", "correctie", "grondprijs_m2_gemeente", "grondprijs_m2_low", "grondprijs_m2_central",
            "grondprijs_m2_high", "verhouding", "binnen_band", "grondaandeel_gemeente", "grondaandeel_central"]
    out = b[cols].rename(columns={"correctie": "buurtcorrectie"}).round(
        {"kavel_m2": 0, "grondprijs_m2_gemeente": 0, "verhouding": 2, "grondaandeel_gemeente": 3})
    out.to_csv(OUT / "vergelijking_grondstaffel.csv", index=False)

    # ------------------------------------------------------------ stability of the official split
    prev = bp[(bp.peildatum == vorig) & (bp.objecttype == typ) & (bp.gebiedssoort == "basisbuurt")].copy()
    naam = {norm(n): code for code, n in bc.buurtnaam.items()}
    prev["buurtcode"] = prev.gebied.map(lambda n: naam.get(norm(n)))
    prev = prev.dropna(subset=["buurtcode"]).join(bc[["waardegebied", "correctie"]], on="buurtcode")
    prev["prijs_nu"] = prev.waardegebied.map(prijs) * (1 + prev.correctie)
    prev["factor"] = prev.prijs_nu / prev.basisprijs_m2
    log("basisbuurten matched", len(prev), "of", int(((bp.peildatum == vorig) & (bp.objecttype == typ)).sum()))

    # ------------------------------------------------------------ summary
    w = ours.dropna(subset=["woningen_bag", "pct_grondgebonden_bag"])
    gg_share = float((w.woningen_bag * w.pct_grondgebonden_bag / 100).sum() / w.woningen_bag.sum())
    r = b.verhouding
    summ = {
        "peildatum": peil, "vorige_peildatum": vorig, "objecttype": typ,
        "grondgebonden_aandeel_woningen": gg_share,
        "buurtcorrecties": len(bc),
        "basisprijs": {k: float(v) for k, v in prijs.items()},
        "buurten": len(b), "woningen": int(b.woningen_bag.sum()),
        "verhouding_mediaan": float(r.median()), "verhouding_p10": float(r.quantile(0.1)),
        "verhouding_p90": float(r.quantile(0.9)),
        "binnen_band": int(b.binnen_band.sum()),
        "rangcorrelatie": float(b.grondprijs_m2_central.rank().corr(b.grondprijs_m2_gemeente.rank())),
        "grondaandeel_gemeente_mediaan": float(b.grondaandeel_gemeente.median()),
        "grondaandeel_ons_mediaan": float(b.grondaandeel_central.median()),
        "stabiliteit": {"basisbuurten": len(prev), "factor_mediaan": float(prev.factor.median()),
                        "factor_min": float(prev.factor.min()), "factor_max": float(prev.factor.max()),
                        "marktontwikkeling": G["marktontwikkeling"],
                        "buurten": prev[["gebied", "buurtcode", "basisprijs_m2", "prijs_nu", "factor"]]
                        .round(2).to_dict("records")},
        "per_waardegebied": [],
    }
    for wg, g in b.groupby("waardegebied"):
        summ["per_waardegebied"].append({
            "waardegebied": wg, "buurten": len(g), "woningen": int(g.woningen_bag.sum()),
            "kavel_m2": float(g.kavel_m2.median()),
            "gemeente_m2": float(g.grondprijs_m2_gemeente.median()),
            "ons_m2": float(g.grondprijs_m2_central.median()),
            "ons_m2_low": float(g.grondprijs_m2_low.median()), "ons_m2_high": float(g.grondprijs_m2_high.median()),
            "aandeel_gemeente": float(g.grondaandeel_gemeente.median()),
            "aandeel_ons": float(g.grondaandeel_central.median())})
    write_json(OUT / "samenvatting_grondstaffel.json", summ, indent=1)

    # ------------------------------------------------------------ site data
    C = read_json(SITE_DATA / "cijfers.json")

    def put(key, raw, text):
        C[key] = {"v": raw, "t": text}

    cheap, dear = prijs.idxmin(), prijs.idxmax()
    s = summ["stabiliteit"]
    put("gs_peildatum", peil, datum(peil))
    put("gs_vorige_peildatum", vorig, datum(vorig))
    put("gs_grondgebonden", gg_share, pct(gg_share))
    put("gs_buurtcorrecties", len(bc), nl(len(bc)))
    put("gs_prijs_min", float(prijs[cheap]), f"{eur(round(prijs[cheap]))} ({cheap})")
    put("gs_prijs_max", float(prijs[dear]), f"{eur(round(prijs[dear]))} ({dear})")
    put("gs_min_pct", G["min_pct_grondgebonden"], pct(G["min_pct_grondgebonden"] / 100))
    put("gs_buurten", summ["buurten"], nl(summ["buurten"]))
    put("gs_woningen", summ["woningen"], nl(summ["woningen"]))
    put("gs_verhouding", summ["verhouding_mediaan"], nl(summ["verhouding_mediaan"], 1))
    put("gs_verhouding_p10", summ["verhouding_p10"], nl(summ["verhouding_p10"], 1))
    put("gs_verhouding_p90", summ["verhouding_p90"], nl(summ["verhouding_p90"], 1))
    put("gs_binnen_band", summ["binnen_band"], nl(summ["binnen_band"]) if summ["binnen_band"] else "geen")
    put("gs_rangcorrelatie", summ["rangcorrelatie"], nl(summ["rangcorrelatie"], 2))
    put("gs_aandeel_gemeente", summ["grondaandeel_gemeente_mediaan"], pct(summ["grondaandeel_gemeente_mediaan"]))
    put("gs_aandeel_ons", summ["grondaandeel_ons_mediaan"], pct(summ["grondaandeel_ons_mediaan"]))
    put("gs_stab_buurten", s["basisbuurten"], nl(s["basisbuurten"]))
    put("gs_stab_mediaan", s["factor_mediaan"], nl(s["factor_mediaan"], 1))
    put("gs_stab_min", s["factor_min"], nl(s["factor_min"], 1))
    put("gs_stab_max", s["factor_max"], nl(s["factor_max"], 1))
    put("gs_markt", s["marktontwikkeling"], pct(s["marktontwikkeling"], 1))
    write_json(SITE_DATA / "cijfers.json", C, indent=1)

    T = read_json(SITE_DATA / "tabellen.json")
    T["grondstaffel"] = [{
        "waardegebied": x["waardegebied"], "buurten": x["buurten"], "kavel": nl(x["kavel_m2"]),
        "gemeente": eur(round(x["gemeente_m2"], -1)), "ons": eur(round(x["ons_m2"], -1)),
        "bereik": f"{eur(round(x['ons_m2_low'], -1))}–{eur(round(x['ons_m2_high'], -1))}",
        "aandeel_gemeente": pct(x["aandeel_gemeente"]), "aandeel_ons": pct(x["aandeel_ons"])}
        for x in summ["per_waardegebied"]]
    write_json(SITE_DATA / "tabellen.json", T, indent=1)
    shutil.copy(OUT / "vergelijking_grondstaffel.csv", SITE_STATIC / "data" / "vergelijking_grondstaffel.csv")
    log("buurten", summ["buurten"], "ratio median", round(summ["verhouding_mediaan"], 2),
        "in band", summ["binnen_band"], "rank corr", round(summ["rangcorrelatie"], 2),
        "stability", round(s["factor_min"], 2), round(s["factor_mediaan"], 2), round(s["factor_max"], 2))


if __name__ == "__main__":
    amsterdam_only()
    main()
