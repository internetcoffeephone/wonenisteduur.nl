# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas>=2.2", "numpy>=1.26"]
# ///
"""Check: the same estimate and grondstaffel comparison for Den Haag.

    AMS_GEMEENTE=denhaag uv run 01_fetch.py     # once; then 02_prepare.py and 03_land.py the same way
    uv run 08_denhaag.py                        (after 07_grondstaffel.py)

In Amsterdam our land prices come out about twice the municipality's
grondstaffel (07_grondstaffel.py). To see whether that is particular to
Amsterdam's model, 03_land.py runs for Den Haag with the same parameters
(params-denhaag.toml only changes the area) and is compared with Den Haag's
grondstaffel the same way. Den Haag prices land per buurt and woningtype
directly, in bands of kavel m2 (input/grondstaffel/denhaag/, from
grondstaffel_denhaag.py):

    official value = staffel(kavel m2) for a rijwoning in the buurt

Also checks how stable Den Haag's prices are: the first band per buurt at three
peildata, next to the change of the mean WOZ value.

Reads only committed files (output/denhaag/, input/grondstaffel/denhaag/). Writes
  output/denhaag/vergelijking_grondstaffel.csv     per buurt
  output/denhaag/samenvatting_grondstaffel.json    aggregates
  data/amsterdam/cijfers.json                      dh_* keys added
  static/amsterdam/data/vergelijking_grondstaffel_denhaag.csv
"""

from __future__ import annotations

import shutil

import pandas as pd

from common import (HERE, OUT, SITE_DATA, SITE_STATIC, amsterdam_only, eur, log, nl, params, pct, read_json,
                    staffel_waarde, write_json)

P = params()
G, D = P["grondstaffel"], P["denhaag"]
DH = OUT / "denhaag"
IN = HERE / "input" / "grondstaffel" / "denhaag"
MAAND = ("januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
         "november", "december")


def datum(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MAAND[m - 1]} {y}"


def spread(s: pd.Series) -> dict:
    return {"mediaan": float(s.median()), "p10": float(s.quantile(0.1)), "p90": float(s.quantile(0.9)),
            "min": float(s.min()), "max": float(s.max())}


def main():
    ours = pd.read_csv(DH / "buurt_grondprijs.csv")
    gs = pd.read_csv(IN / "grondstaffel.csv")
    gs = gs[gs.type == D["objecttype"]]
    names = ours.set_index("buurtcode").buurtnaam
    log("staffel buurten without a CBS buurt:", sorted(set(gs.woz_code[~gs.buurtcode.isin(names.index)])))

    # ------------------------------------------------------------ per buurt
    peil = gs[gs.peildatum == D["peildatum"]].sort_values("van_m2")
    bands = {code: (list(g.van_m2), list(g.prijs_m2)) for code, g in peil.groupby("buurtcode")}
    b = ours[(ours.bron_grondprijs == "buurt") & (ours.pct_grondgebonden_bag >= G["min_pct_grondgebonden"])
             & ours.buurtcode.isin(bands)].copy()
    b["woz_code"] = b.buurtcode.map(peil.groupby("buurtcode").woz_code.first())
    b["kavel_m2"] = b.grond_m2_per_woning
    b["prijs_eerste_band"] = b.buurtcode.map(lambda c: bands[c][1][0])
    b["grondwaarde_gemeente"] = [staffel_waarde(a, *bands[c]) for a, c in zip(b.kavel_m2, b.buurtcode)]
    b["grondprijs_m2_gemeente"] = b.grondwaarde_gemeente / b.kavel_m2
    b["grondaandeel_gemeente"] = b.grondwaarde_gemeente / b.woz_gem
    b["verhouding"] = b.grondprijs_m2_central / b.grondprijs_m2_gemeente
    b["binnen_band"] = b.grondprijs_m2_gemeente.between(b.grondprijs_m2_low, b.grondprijs_m2_high)
    cols = ["buurtcode", "buurtnaam", "woz_code", "woningen_bag", "pct_grondgebonden_bag", "woz_gem", "kavel_m2",
            "prijs_eerste_band", "grondprijs_m2_gemeente", "grondprijs_m2_low", "grondprijs_m2_central",
            "grondprijs_m2_high", "verhouding", "binnen_band", "grondaandeel_gemeente", "grondaandeel_central"]
    b[cols].round({"kavel_m2": 0, "grondprijs_m2_gemeente": 0, "verhouding": 2, "grondaandeel_gemeente": 3}).to_csv(
        DH / "vergelijking_grondstaffel.csv", index=False)

    # ------------------------------------------------------------ stability: first band per buurt and peildatum
    first = gs[gs.van_m2 == 0].pivot_table(index="buurtcode", columns="peildatum", values="prijs_m2")
    first = first[first.index.isin(names.index)].dropna()
    woz = D["woz_gemiddeld"]
    steps = []
    for a, z in zip(D["peildata"], D["peildata"][1:]):
        f = first[z] / first[a]
        steps.append({"van": a, "tot": z, "buurten": len(first), **spread(f), "gelijk": float((f == 1).mean()),
                      "woz": woz[z] / woz[a]})

    # ------------------------------------------------------------ summary
    w = ours.dropna(subset=["woningen_bag", "pct_grondgebonden_bag"])
    gg_share = float((w.woningen_bag * w.pct_grondgebonden_bag / 100).sum() / w.woningen_bag.sum())
    r = b.verhouding
    summ = {
        "peildatum": D["peildatum"], "objecttype": D["objecttype"],
        "grondgebonden_aandeel_woningen": gg_share,
        "buurten_staffel": int(peil.buurtcode[peil.buurtcode.isin(names.index)].nunique()),
        "prijs_eerste_band": spread(first[D["peildatum"]]),
        # Most compared buurten share one price for the first band; differences then come from kavel size.
        "prijs_eerste_band_meest": float(b.prijs_eerste_band.mode()[0]),
        "buurten_prijs_meest": int((b.prijs_eerste_band == b.prijs_eerste_band.mode()[0]).sum()),
        "buurten": len(b), "woningen": int(b.woningen_bag.sum()),
        "verhouding_mediaan": float(r.median()), "verhouding_p10": float(r.quantile(0.1)),
        "verhouding_p90": float(r.quantile(0.9)),
        "binnen_band": int(b.binnen_band.sum()),
        "rangcorrelatie": float(b.grondprijs_m2_central.rank().corr(b.grondprijs_m2_gemeente.rank())),
        "grondaandeel_gemeente_mediaan": float(b.grondaandeel_gemeente.median()),
        "grondaandeel_ons_mediaan": float(b.grondaandeel_central.median()),
        "stabiliteit": steps,
    }
    write_json(DH / "samenvatting_grondstaffel.json", summ, indent=1)

    # ------------------------------------------------------------ site data
    C = read_json(SITE_DATA / "cijfers.json")

    def put(key, raw, text):
        C[key] = {"v": raw, "t": text}

    put("dh_peildatum", D["peildatum"], datum(D["peildatum"]))
    put("dh_grondgebonden", gg_share, pct(gg_share))
    put("dh_buurten_staffel", summ["buurten_staffel"], nl(summ["buurten_staffel"]))
    put("dh_buurten", summ["buurten"], nl(summ["buurten"]))
    put("dh_woningen", summ["woningen"], nl(summ["woningen"]))
    put("dh_verhouding", summ["verhouding_mediaan"], nl(summ["verhouding_mediaan"], 1))
    put("dh_verhouding_p10", summ["verhouding_p10"], nl(summ["verhouding_p10"], 1))
    put("dh_verhouding_p90", summ["verhouding_p90"], nl(summ["verhouding_p90"], 1))
    put("dh_binnen_band", summ["binnen_band"], nl(summ["binnen_band"]) if summ["binnen_band"] else "geen")
    put("dh_rangcorrelatie", summ["rangcorrelatie"], nl(summ["rangcorrelatie"], 2))
    put("dh_prijs_meest", summ["prijs_eerste_band_meest"], eur(summ["prijs_eerste_band_meest"]))
    put("dh_prijs_meest_buurten", summ["buurten_prijs_meest"], nl(summ["buurten_prijs_meest"]))
    put("dh_aandeel_gemeente", summ["grondaandeel_gemeente_mediaan"], pct(summ["grondaandeel_gemeente_mediaan"]))
    put("dh_aandeel_ons", summ["grondaandeel_ons_mediaan"], pct(summ["grondaandeel_ons_mediaan"]))
    for i, s in enumerate(steps, 1):
        put(f"dh_stab{i}_van", s["van"], datum(s["van"]))
        put(f"dh_stab{i}_tot", s["tot"], datum(s["tot"]))
        put(f"dh_stab{i}_mediaan", s["mediaan"] - 1, pct(s["mediaan"] - 1))
        put(f"dh_stab{i}_woz", s["woz"] - 1, pct(s["woz"] - 1, 1))
        put(f"dh_stab{i}_gelijk", s["gelijk"], pct(s["gelijk"]))
    put("dh_stab_buurten", len(first), nl(len(first)))
    lo, hi = min(s["min"] for s in steps), max(s["max"] for s in steps)
    put("dh_stab_min", lo - 1, pct(lo - 1, sign=True))
    put("dh_stab_max", hi - 1, pct(hi - 1, sign=True))
    write_json(SITE_DATA / "cijfers.json", C, indent=1)
    shutil.copy(DH / "vergelijking_grondstaffel.csv", SITE_STATIC / "data" / "vergelijking_grondstaffel_denhaag.csv")
    log("buurten", summ["buurten"], "ratio median", round(summ["verhouding_mediaan"], 2),
        "p10-p90", round(summ["verhouding_p10"], 2), round(summ["verhouding_p90"], 2),
        "in band", summ["binnen_band"], "rank corr", round(summ["rangcorrelatie"], 2),
        "share official/ours", round(summ["grondaandeel_gemeente_mediaan"], 2),
        round(summ["grondaandeel_ons_mediaan"], 2))
    for s in steps:
        log("first band", s["van"], "->", s["tot"], {k: round(v, 3) for k, v in s.items() if isinstance(v, float)})


if __name__ == "__main__":
    amsterdam_only()
    main()
