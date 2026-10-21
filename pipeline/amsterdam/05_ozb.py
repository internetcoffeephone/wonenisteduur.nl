# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyarrow>=15", "pandas>=2.2", "numpy>=1.26"]
# ///
"""Deliverable C: who wins and who loses if the OZB on woningen shifts to land.

Static, first-year, woningen only. For every dwelling in a buurt with a usable
CBS WOZ average the model builds an estimated value from its parts:

    woz_i      = CBS buurt average x dwellings x (floor area / buurt floor area)
                 i.e. one WOZ per m2 floor area within a buurt
    land_i     = buurt land value x (dwelling's land m2 / buurt land m2), where the
                 land m2 is the median land per m2 floor area of the dwelling's
                 type (appartement / grondgebonden) in its buurt x its floor area.
                 One land price per m2 within a buurt (Doucet); using the type
                 median keeps single large parcels from dominating a buurt.
    gebouw_i   = buurt building value x (dwelling's depreciated rebuild cost / buurt total)

Within a buurt woz_i and land_i + gebouw_i differ dwelling by dwelling; they
add up to the same buurt total. That difference is the point of a land tax:
a dwelling with much land per m2 floor area pays more, a dwelling with little
land pays less.

Current OZB is the 2026 revenue from woningen (CBS 83642NED) spread over these
values; the two variants raise the same revenue from

    A  land only:                 t_L x land_i
    B  land 3x building (3:1):    3 t_B x land_i + t_B x gebouw_i

Per-dwelling results are model output, not observed values, and are never
published. Only buurt and city aggregates are written.

    uv run 05_ozb.py
"""

from __future__ import annotations

import html
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from common import OUT, RAW, WORK, ensure_dirs, log, params, read_json, write_json

P = params()
Z = P["ozb"]


def revenue_2026() -> float:
    rows = read_json(RAW / "cbs" / "83642NED_ams.json")["rows"]
    r = [x for x in rows if x["GemeentelijkeHeffingenVanaf2017"].strip() == "A047000" and x["Perioden"] == Z["year"]]
    return r[0]["GemeentelijkeHeffingenIn1000Euro_1"] * 1000.0


def verify_tariff() -> dict:
    """Read the tariff for woningen from the CVDR XML and check it against params."""
    xml = (RAW / "cvdr" / f"{Z['cvdr_id']}.xml").read_text(encoding="utf-8")
    text = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)))
    m = re.search(r"eigenarenbelasting:\s*voor onroerende zaken die in hoofdzaak tot woning dienen:\s*"
                  r"([0-9]+,[0-9]+)\s*%", text, flags=re.IGNORECASE)
    start = re.search(r"De datum van ingang van heffing is ([0-9]+ \w+ [0-9]{4})", text)
    found = float(m.group(1).replace(",", ".")) / 100 if m else None
    if found is None or abs(found - Z["tariff_woningen_2026"]) > 1e-9:
        raise SystemExit(f"OZB tariff in {Z['cvdr_id']} is {found}, params say {Z['tariff_woningen_2026']}")
    return {"tarief": found, "ingang": start.group(1) if start else None, "cvdr": Z["cvdr_id"]}


def wmedian(v, w=None) -> float:
    v = np.asarray(v, dtype=float)
    w = np.ones_like(v) if w is None else np.asarray(w, dtype=float)
    o = np.argsort(v)
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, 0.5 * c[-1])]) if len(v) else float("nan")


def main():
    ensure_dirs()
    tariff = verify_tariff()
    R = revenue_2026()
    b = gpd.read_parquet(WORK / "buurt_land.parquet")
    d = pd.read_parquet(WORK / "dwellings.parquet")
    n_all = len(d)
    ok = b[b.woz_bruikbaar & b.grondaandeel_central.notna()].set_index("buurtcode")
    d = d[d.buurtcode.isin(ok.index) & d.land_m2.notna() & (d.land_m2 > 0)].copy()
    log("dwellings in model", len(d), "of", n_all)

    # Typical land per m2 floor area per buurt x type (median; buurt median for small groups).
    d["intens"] = d.land_m2 / d.opp
    grp = d.groupby(["buurtcode", "type"]).intens
    med_bt, n_bt = grp.transform("median"), grp.transform("size")
    d["land_typ"] = np.where(n_bt >= 5, med_bt, d.groupby("buurtcode").intens.transform("median")) * d.opp
    g = d.groupby("buurtcode")
    land_sum, drc_sum, opp_sum, n = g.land_typ.sum(), g.drc_central.sum(), g.opp.sum(), g.size()
    woz_b = ok.woz_gem.reindex(n.index) * n
    a = ok.grondaandeel_central.reindex(n.index)
    d["land"] = (a * woz_b).reindex(d.buurtcode).values * d.land_typ / land_sum.reindex(d.buurtcode).values
    d["gebouw"] = ((1 - a) * woz_b).reindex(d.buurtcode).values * d.drc_central / drc_sum.reindex(d.buurtcode).values
    d["woz"] = woz_b.reindex(d.buurtcode).values * d.opp / opp_sum.reindex(d.buurtcode).values

    # The 2026 revenue applies to all woningen; the model covers most of them.
    cbs_gm = read_json(RAW / "cbs" / f"{P['area']['cbs_kerncijfers']}_ams.json")["rows"]
    gm = next(r for r in cbs_gm if r["WijkenEnBuurten"].strip() == P["area"]["gemeentecode"])
    woz_gemeente = gm["GemiddeldeWOZWaardeVanWoningen_39"] * 1000.0 * gm["Woningvoorraad_35"]
    t0 = R / woz_gemeente
    R_model = t0 * d.woz.sum()
    L, B = d.land.sum(), d.gebouw.sum()
    t_land = R_model / L
    k = Z["land_building_ratio"]
    t_b = R_model / (k * L + B)
    rates = {"t_huidig": t0, "t_officieel_2026": tariff["tarief"], "A_t_grond": t_land,
             "B_t_grond": k * t_b, "B_t_gebouw": t_b}
    log("rates (% of value)", {kk: round(v * 100, 4) for kk, v in rates.items()})

    d["ozb_nu"] = t0 * d.woz
    d["ozb_A"] = t_land * d.land
    d["ozb_B"] = k * t_b * d.land + t_b * d.gebouw
    for v in ("A", "B"):
        assert abs(d[f"ozb_{v}"].sum() / d.ozb_nu.sum() - 1) < 1e-9, "variant is not revenue-neutral"
        d[f"d_{v}"] = d[f"ozb_{v}"] - d.ozb_nu
        d[f"p_{v}"] = d[f"ozb_{v}"] / d.ozb_nu - 1

    thr = Z["change_threshold"]
    bi = ok[["buurtnaam", "wijknaam", "stadsdeel", "inkomen_gem", "pct_laag_inkomen", "woz_gem"]]
    d = d.join(bi[["stadsdeel", "inkomen_gem"]], on="buurtcode")

    # Buurt x type: the typical (median) dwelling.
    rows = []
    for (bc, typ), grp in d.groupby(["buurtcode", "type"]):
        if len(grp) < 20:
            continue
        rows.append({"buurtcode": bc, "type": typ, "woningen": len(grp),
                     "ozb_nu_med": grp.ozb_nu.median(), "woz_model_med": grp.woz.median(),
                     **{f"{m}_{v}_med": grp[f"{m}_{v}"].median() for v in ("A", "B") for m in ("ozb", "d", "p")}})
    bt = pd.DataFrame(rows).merge(bi, left_on="buurtcode", right_index=True)
    # Whole buurt (all types) for the map.
    rows = []
    for bc, grp in d.groupby("buurtcode"):
        rows.append({"buurtcode": bc, "woningen_model": len(grp),
                     "pct_grondgebonden": 100 * (grp.type == "grondgebonden").mean(),
                     "ozb_nu_med": grp.ozb_nu.median(),
                     **{f"{m}_{v}_med": grp[f"{m}_{v}"].median() for v in ("A", "B") for m in ("ozb", "d", "p")},
                     **{f"aandeel_plus10_{v}": (grp[f"p_{v}"] > thr).mean() for v in ("A", "B")},
                     **{f"aandeel_min10_{v}": (grp[f"p_{v}"] < -thr).mean() for v in ("A", "B")}})
    bb = pd.DataFrame(rows).merge(bi, left_on="buurtcode", right_index=True)

    # Income quintiles of buurten, weighted by dwellings in the model.
    inc = bb.dropna(subset=["inkomen_gem"]).sort_values("inkomen_gem")
    cum = inc.woningen_model.cumsum() / inc.woningen_model.sum()
    inc["kwintiel"] = np.minimum((cum.values * 5 - 1e-9).astype(int) + 1, 5)
    bb = bb.merge(inc[["buurtcode", "kwintiel"]], on="buurtcode", how="left")
    d = d.merge(inc[["buurtcode", "kwintiel"]], on="buurtcode", how="left")

    def summarise(grp) -> dict:
        return {"woningen": int(len(grp)), "ozb_nu_med": float(grp.ozb_nu.median()),
                **{f"{m}_{v}_med": float(grp[f"{m}_{v}"].median()) for v in ("A", "B") for m in ("ozb", "d", "p")},
                **{f"aandeel_plus10_{v}": float((grp[f"p_{v}"] > thr).mean()) for v in ("A", "B")},
                **{f"aandeel_min10_{v}": float((grp[f"p_{v}"] < -thr).mean()) for v in ("A", "B")}}

    s = {
        "opbrengst_2026": R, "tarief": tariff, "rates": rates,
        "woz_gemeente_cbs": woz_gemeente, "woz_model": float(d.woz.sum()), "opbrengst_model": R_model,
        "grond_model": float(L), "gebouw_model": float(B),
        "woningen_bag": int(n_all), "woningen_model": int(len(d)),
        "stad": summarise(d),
        "per_type": {t: summarise(grp) for t, grp in d.groupby("type")},
        "per_kwintiel": {int(q): {**summarise(grp), "inkomen_min": float(inc[inc.kwintiel == q].inkomen_gem.min()),
                                  "inkomen_max": float(inc[inc.kwintiel == q].inkomen_gem.max())}
                         for q, grp in d.dropna(subset=["kwintiel"]).groupby("kwintiel")},
        "per_kwintiel_type": {f"{int(q)}_{t}": summarise(grp)
                              for (q, t), grp in d.dropna(subset=["kwintiel"]).groupby(["kwintiel", "type"])},
        "per_stadsdeel": {sd: summarise(grp) for sd, grp in d.groupby("stadsdeel")},
        "buurten": {f"aandeel_buurten_plus10_{v}": float((bb[f"p_{v}_med"] > thr).mean()) for v in ("A", "B")}
        | {f"aandeel_buurten_min10_{v}": float((bb[f"p_{v}_med"] < -thr).mean()) for v in ("A", "B")}
        | {"aantal": int(len(bb))},
    }
    # Histogram of % change (dwellings), 5-point bins from -100% to +200%.
    edges = np.arange(-1.0, 2.05, 0.05)
    for v in ("A", "B"):
        h, _ = np.histogram(d[f"p_{v}"].clip(-1, 2 - 1e-9), bins=edges)
        s[f"histogram_{v}"] = {"edges": [round(x, 2) for x in edges], "counts": h.tolist()}
    write_json(WORK / "summary_ozb.json", s, indent=1)
    write_json(OUT / "samenvatting_ozb.json", s, indent=1)

    num = bt.select_dtypes("number").columns
    bt[num] = bt[num].round(3)
    bt.to_csv(OUT / "ozb_buurt_type.csv", index=False)
    num = bb.select_dtypes("number").columns
    bb[num] = bb[num].round(3)
    bb.to_csv(OUT / "ozb_buurt.csv", index=False)
    bb.to_parquet(WORK / "ozb_buurt.parquet")
    log("stad", s["stad"])
    log("per type", s["per_type"])
    log("per kwintiel", {q: (round(v["p_A_med"], 3), round(v["p_B_med"], 3), v["inkomen_min"], v["inkomen_max"])
                         for q, v in s["per_kwintiel"].items()})
    log("buurten", s["buurten"])


if __name__ == "__main__":
    main()
