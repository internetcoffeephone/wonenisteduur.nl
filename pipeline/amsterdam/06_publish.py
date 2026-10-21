# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyarrow>=15", "shapely>=2.0", "pandas>=2.2", "numpy>=1.26", "matplotlib>=3.8"]
# ///
"""Deliverable D (data side): files the Hugo pages read.

    uv run 06_publish.py

Writes
  data/amsterdam/cijfers.json        headline numbers (raw + Dutch-formatted text)
  data/amsterdam/tabellen.json       rows for the HTML tables (chart twins, top 20)
  static/amsterdam/data/*.geojson    simplified map layers (buurten, parkeerterreinen)
  static/amsterdam/data/*.csv        downloads (same as pipeline/amsterdam/output)
  static/amsterdam/grafieken/*.svg   charts, inlined by the page
  static/amsterdam/kaart-*.png       static map fallbacks (print, no-JS, social)
"""

from __future__ import annotations

import html
import math
import shutil

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

from common import OUT, SITE_DATA, SITE_STATIC, WORK, ensure_dirs, log, params, read_json, write_json

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

P = params()

# Site palette and the validated chart colours (see README, "Kleuren").
INK, INK2, MUTED = "#2c2c2c", "#5b5a56", "#8a877f"
NAVY, SAGE, BG, BORDER, GRID = "#2c3e50", "#7a9e5a", "#fafaf8", "#e0ddd6", "#e6e3dc"
SEQ = ["#e1edd4", "#c2d6ac", "#a5be87", "#87a463", "#6d8848", "#526932", "#3a4c21"]
DIV = ["#0b4c92", "#407bc5", "#a0c0eb", "#dfdeda", "#e5b099", "#df6c32", "#a14206"]
DOWN, UP, NEUTRAL = "#407bc5", "#df6c32", "#d6d4cd"
NODATA = "#efede8"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif"


# ---------------------------------------------------------------- formatting
def nl(x: float, d: int = 0) -> str:
    s = f"{x:,.{d}f}"
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")


# U+2060 (word joiner) keeps a sign glued to its number when text wraps.
SIGN_UP, SIGN_DOWN = "+\u2060", "\u2212\u2060"


def pct(x: float, d: int = 0, sign: bool = False) -> str:
    v = x * 100
    s = nl(abs(v), d)
    if sign:
        return (SIGN_UP if v > 0 else SIGN_DOWN if v < 0 else "") + s + "%"
    return s + "%"


def eur(x: float, sign: bool = False) -> str:
    s = "\u20ac" + nl(abs(x))
    if sign:
        return (SIGN_UP if x > 0 else SIGN_DOWN if x < 0 else "") + s
    return s


def mld(x: float, d: int = 1) -> str:
    return nl(x / 1e9, d)


def nice_breaks(values, weights, n=7, step=500):
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    m = ~np.isnan(v)
    v, w = v[m], w[m]
    o = np.argsort(v)
    c = np.cumsum(w[o]) / w.sum()
    qs = [v[o][np.searchsorted(c, k / n)] for k in range(1, n)]
    out = []
    for q in qs:
        b = round(q / step) * step
        if not out or b > out[-1]:
            out.append(int(b))
    return out


# ---------------------------------------------------------------- headline numbers
def build_numbers(sl, sp, so, land):
    C = {}

    def put(key, raw, text):
        C[key] = {"v": raw, "t": text}

    rc = sl["rebuild_cost"]
    put("bouwkosten_cbs", rc["base_excl_btw"], eur(rc["base_excl_btw"]))
    for v in ("low", "central", "high"):
        put(f"bouwkosten_{v}", rc[v], eur(round(rc[v], -1)))
    put("kalibratie", rc.get("calibration_factor", 1.0), nl(rc.get("calibration_factor", 1.0), 2))
    nat, nc = sl["national_land_share"], sl["national_check"]
    put("cbs_grondaandeel_nl", nat["share"], pct(nat["share"]))
    put("cbs_grondaandeel_jaar", nat["year"], nat["year"])
    put("nl_check_low", nc["share_low"], pct(nc["share_low"]))
    put("nl_check_high", nc["share_high"], pct(nc["share_high"]))
    put("woz_som", sl["woz_som"], mld(sl["woz_som"], 0))
    put("woz_gem", sl["woz_gem_gemeente"], eur(sl["woz_gem_gemeente"]))
    put("woningen_bag", sl["dwellings_bag"], nl(sl["dwellings_bag"]))
    put("woningen_cbs", sl["dwellings_cbs_gemeente"], nl(sl["dwellings_cbs_gemeente"]))
    for v in ("low", "central", "high"):
        put(f"grondwaarde_{v}", sl[f"grondwaarde_woningen_{v}"], mld(sl[f"grondwaarde_woningen_{v}"], 0))
        put(f"grondaandeel_{v}", sl[f"grondaandeel_gem_{v}"], pct(sl[f"grondaandeel_gem_{v}"]))
        put(f"grondprijs_med_{v}", sl[f"grondprijs_m2_median_woning_{v}"],
            eur(round(sl[f"grondprijs_m2_median_woning_{v}"], -2)))
        put(f"grondwaarde_wo_med_{v}", sl[f"grondwaarde_m2_wo_median_woning_{v}"],
            eur(round(sl[f"grondwaarde_m2_wo_median_woning_{v}"], -2)))
        put(f"grondprijs_std_med_{v}", sl[f"grondprijs_m2_std_median_woning_{v}"],
            eur(round(sl[f"grondprijs_m2_std_median_woning_{v}"], -2)))
    put("dichtheid_ref", sl["dichtheid_ref"], nl(sl["dichtheid_ref"], 1))
    put("buurten", sl["buurten"], nl(sl["buurten"]))
    put("buurten_eigen", sl["buurten_eigen_schatting"], nl(sl["buurten_eigen_schatting"]))
    put("buurten_wijk", sl["buurten_wijk"], nl(sl["buurten_wijk"]))
    put("buurten_geen", sl["buurten_geen"], nl(sl["buurten_geen"]))
    put("bsq_boven_plafond", sl["bsq_cap_binds_share_buurten"], pct(sl["bsq_cap_binds_share_buurten"]))
    put("cv_median", sl["cv_woz_m2_median"], pct(sl["cv_woz_m2_median"], 1))
    put("cv_boven_25", sl["cv_woz_m2_share_gt_025"], pct(sl["cv_woz_m2_share_gt_025"], 1))
    put("cv_buurten", sl["cv_buurten"], nl(sl["cv_buurten"]))
    al = sl["allocation"]
    put("percelen", al["percelen_totaal"], nl(al["percelen_totaal"]))
    put("percelen_afgetopt", al["percelen_afgetopt"], nl(al["percelen_afgetopt"]))
    put("woongrond_ha", float(land.grond_m2_som.sum()) / 1e4, nl(float(land.grond_m2_som.sum()) / 1e4))

    t, s_ = sp["terrein"], sp["straat"]
    put("park_aantal", t["aantal"], nl(t["aantal"]))
    put("park_ha", t["m2_onbebouwd"] / 1e4, nl(t["m2_onbebouwd"] / 1e4))
    put("park_ha_gewaardeerd", t["m2_gewaardeerd"] / 1e4, nl(t["m2_gewaardeerd"] / 1e4))
    put("park_aantal_gewaardeerd", t["aantal_gewaardeerd"], nl(t["aantal_gewaardeerd"]))
    put("park_ha_geen_tarief", t["m2_geen_eigen_tarief"] / 1e4, nl(t["m2_geen_eigen_tarief"] / 1e4))
    for v in ("low", "central", "high"):
        put(f"park_waarde_{v}", t[f"waarde_{v}"], mld(t[f"waarde_{v}"]))
        put(f"park_indicatief_{v}", t[f"waarde_indicatief_{v}"], mld(t[f"waarde_indicatief_{v}"]))
        put(f"straat_waarde_{v}", s_[f"waarde_{v}"], mld(s_[f"waarde_{v}"], 0))
    put("straat_ha", s_["m2"] / 1e4, nl(s_["m2"] / 1e4))
    put("gebouwd_aantal", sp["gebouwd"]["aantal"], nl(sp["gebouwd"]["aantal"]))
    put("top20_aandeel", sp["top20_aandeel_central"], pct(sp["top20_aandeel_central"]))
    put("park_kandidaten_bgt", sp["kandidaten"]["bgt"], nl(sp["kandidaten"]["bgt"]))
    put("park_kandidaten_osm", sp["kandidaten"]["osm"], nl(sp["kandidaten"]["osm"]))

    # Municipal revenue context (CBS 83642NED, 2026 voorlopig).
    rows = read_json(WORK.parent / "raw" / "cbs" / "83642NED_ams.json")["rows"]
    rev = {r["GemeentelijkeHeffingenVanaf2017"].strip(): r["GemeentelijkeHeffingenIn1000Euro_1"] * 1000
           for r in rows if r["Perioden"] == P["ozb"]["year"]}
    put("ozb_totaal", rev["A046999"], nl(rev["A046999"] / 1e6))
    put("ozb_woningen", rev["A047000"], nl(rev["A047000"] / 1e6, 1))
    put("ozb_nietwoningen", rev["A047001"], nl(rev["A047001"] / 1e6))
    put("parkeerheffingen", rev["A047002"], nl(rev["A047002"] / 1e6))

    r = so["rates"]
    put("tarief_officieel", r["t_officieel_2026"], nl(r["t_officieel_2026"] * 100, 4) + "%")
    put("tarief_model", r["t_huidig"], nl(r["t_huidig"] * 100, 4) + "%")
    put("tarief_A_grond", r["A_t_grond"], nl(r["A_t_grond"] * 100, 4) + "%")
    put("tarief_B_grond", r["B_t_grond"], nl(r["B_t_grond"] * 100, 4) + "%")
    put("tarief_B_gebouw", r["B_t_gebouw"], nl(r["B_t_gebouw"] * 100, 4) + "%")
    put("ozb_tarief_ingang", so["tarief"]["ingang"], so["tarief"]["ingang"])
    put("woningen_model", so["woningen_model"], nl(so["woningen_model"]))
    put("woningen_model_pct", so["woningen_model"] / so["woningen_bag"], pct(so["woningen_model"] / so["woningen_bag"]))
    groups = {"stad": so["stad"], **{f"type_{k}": v for k, v in so["per_type"].items()},
              **{f"kw{k}": v for k, v in so["per_kwintiel"].items()}}
    for g, s in groups.items():
        for var in ("A", "B"):
            put(f"{g}_p_{var}", s[f"p_{var}_med"], pct(s[f"p_{var}_med"], 1, sign=True))
            put(f"{g}_d_{var}", s[f"d_{var}_med"], eur(round(s[f"d_{var}_med"]), sign=True))
            put(f"{g}_plus10_{var}", s[f"aandeel_plus10_{var}"], pct(s[f"aandeel_plus10_{var}"]))
            put(f"{g}_min10_{var}", s[f"aandeel_min10_{var}"], pct(s[f"aandeel_min10_{var}"]))
        put(f"{g}_ozb_nu", s["ozb_nu_med"], eur(round(s["ozb_nu_med"])))
        put(f"{g}_woningen", s["woningen"], nl(s["woningen"]))
    for var in ("A", "B"):
        b = so["buurten"]
        put(f"buurten_plus10_{var}", b[f"aandeel_buurten_plus10_{var}"], pct(b[f"aandeel_buurten_plus10_{var}"]))
        put(f"buurten_min10_{var}", b[f"aandeel_buurten_min10_{var}"], pct(b[f"aandeel_buurten_min10_{var}"]))
    put("ozb_buurten", so["buurten"]["aantal"], nl(so["buurten"]["aantal"]))

    # Parameters (params.toml), so the method page cannot drift from the pipeline.
    rcp, dep, ls_, la, pk = P["rebuild_cost"], P["depreciation"], P["land_share"], P["land_area"], P["parking"]
    for v in ("low", "central", "high"):
        put(f"p_bijkomend_{v}", rcp["bijkomend"][v], pct(rcp["bijkomend"][v] - 1))
        put(f"p_toeslag_{v}", rcp["premium"][v], pct(rcp["premium"][v] - 1))
    for k in ("low_land", "central", "high_land"):
        put(f"p_levensduur_{k}", dep["life"][k], nl(dep["life"][k]))
        put(f"p_restwaarde_{k}", dep["floor"][k], pct(dep["floor"][k]))
    put("p_btw", rcp["btw"], pct(rcp["btw"] - 1))
    put("p_cbs_jaar", rcp["cbs_year"], str(rcp["cbs_year"]))
    put("p_clip_min", ls_["clip_min"], pct(ls_["clip_min"]))
    put("p_clip_max", ls_["clip_max"], pct(ls_["clip_max"]))
    put("p_krimp_k", ls_["shrink_k"], nl(ls_["shrink_k"]))
    for n_ in (100, 1000):
        put(f"p_gewicht_{n_}", n_ / (n_ + ls_["shrink_k"]), pct(n_ / (n_ + ls_["shrink_k"])))
    put("p_min_woningen", ls_["min_dwellings"], nl(ls_["min_dwellings"]))
    put("p_min_woz_m2", ls_["min_woz_m2_frac"], pct(ls_["min_woz_m2_frac"]))
    put("p_telling_min", ls_["count_ratio_range"][0], nl(ls_["count_ratio_range"][0], 1))
    put("p_telling_max", ls_["count_ratio_range"][1], nl(ls_["count_ratio_range"][1], 1))
    put("p_cap_m2", la["cap_min_parcel_m2"], nl(la["cap_min_parcel_m2"]))
    put("p_cap_maal", la["cap_footprint_multiple"], nl(la["cap_footprint_multiple"]))
    put("p_min_lot", pk["min_lot_m2"], nl(pk["min_lot_m2"]))
    put("p_strook_breedte", pk["strip_max_width_m"], nl(pk["strip_max_width_m"]))
    put("p_strook_rek", pk["strip_min_elongation"], nl(pk["strip_min_elongation"]))
    put("p_rijbaan", pk["carriageway_touch_frac"], pct(pk["carriageway_touch_frac"]))
    put("p_gebouwd", pk["structure_overlap"], pct(pk["structure_overlap"]))
    put("p_verhouding", P["ozb"]["land_building_ratio"], nl(P["ozb"]["land_building_ratio"]))
    put("p_max_vbo", P["house_type"]["max_vbo_in_pand"], nl(P["house_type"]["max_vbo_in_pand"]))
    return C


# ---------------------------------------------------------------- SVG charts
def _bar_path(x0, x1, y, h, r=4):
    """Bar from baseline x0 to data end x1, rounded only at the data end."""
    if abs(x1 - x0) < 0.5:
        return ""
    r = min(r, abs(x1 - x0), h / 2)
    if x1 >= x0:
        return (f"M{x0:.1f},{y:.1f}H{x1 - r:.1f}Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f}"
                f"V{y + h - r:.1f}Q{x1:.1f},{y + h:.1f} {x1 - r:.1f},{y + h:.1f}H{x0:.1f}Z")
    return (f"M{x0:.1f},{y:.1f}H{x1 + r:.1f}Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f}"
            f"V{y + h - r:.1f}Q{x1:.1f},{y + h:.1f} {x1 + r:.1f},{y + h:.1f}H{x0:.1f}Z")


def svg_diverging_bars(rows, title, desc, fname, ticks):
    """rows: [(label, value_fraction, value_text, tooltip)] - one series, colour by sign."""
    W, left, right, rh, bh, top = 680, 200, 110, 40, 20, 34
    H = top + rh * len(rows) + 30
    lo, hi = min(ticks), max(ticks)
    sx = lambda v: left + (v - lo) / (hi - lo) * (W - left - right)  # noqa: E731
    x0 = sx(0)
    e = html.escape
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{fname}-t {fname}-d" '
           f'class="ams-grafiek" font-family="{FONT}">',
           f'<title id="{fname}-t">{e(title)}</title><desc id="{fname}-d">{e(desc)}</desc>']
    for t in ticks:
        x = sx(t)
        out.append(f'<line x1="{x:.1f}" y1="{top - 8}" x2="{x:.1f}" y2="{H - 26}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{H - 8}" font-size="13" fill="{MUTED}" text-anchor="middle">'
                   f'{e(pct(t, 0, sign=True))}</text>')
    out.append(f'<line x1="{x0:.1f}" y1="{top - 8}" x2="{x0:.1f}" y2="{H - 26}" stroke="#a9a69e" stroke-width="1"/>')
    for i, (label, v, vtext, tip) in enumerate(rows):
        y = top + i * rh + (rh - bh) / 2
        xv = sx(max(lo, min(hi, v)))
        color = UP if v > 0 else DOWN
        out.append(f'<g class="ams-mark"><title>{e(tip)}</title>'
                   f'<rect x="{left - 190}" y="{y - 8:.1f}" width="{W - left + 190}" height="{bh + 16}" fill="transparent"/>'
                   f'<path d="{_bar_path(x0, xv, y, bh)}" fill="{color}"/></g>')
        out.append(f'<text x="{left - 12}" y="{y + bh / 2 + 5:.1f}" font-size="14" fill="{INK}" text-anchor="end">{e(label)}</text>')
        # Value label on the far side of the zero line, so it never runs into the category labels.
        tx, anchor = (x0 - 8, "end") if v >= 0 else (x0 + 8, "start")
        out.append(f'<text x="{tx:.1f}" y="{y + bh / 2 + 5:.1f}" font-size="14" fill="{INK}" text-anchor="{anchor}" '
                   f'font-weight="600">{e(vtext)}</text>')
    out.append("</svg>")
    (SITE_STATIC / "grafieken" / f"{fname}.svg").write_text("\n".join(out) + "\n", encoding="utf-8")


def svg_share_bars(rows, title, desc, fname):
    """rows: [(label, share_down, share_mid, share_up)] - 100% diverging stacked bars."""
    W, left, right, rh, bh, top = 680, 200, 20, 40, 22, 56
    H = top + rh * len(rows) + 10
    sx = lambda f: left + f * (W - left - right)  # noqa: E731
    e = html.escape
    names = [("meer dan 10% minder", DOWN, "#ffffff"), ("tussen −10% en +10%", NEUTRAL, INK),
             ("meer dan 10% meer", UP, INK)]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{fname}-t {fname}-d" '
           f'class="ams-grafiek" font-family="{FONT}">',
           f'<title id="{fname}-t">{e(title)}</title><desc id="{fname}-d">{e(desc)}</desc>']
    lx = 12
    for name, col, _ in names:
        out.append(f'<rect x="{lx}" y="10" width="14" height="14" rx="3" fill="{col}"/>'
                   f'<text x="{lx + 20}" y="22" font-size="13" fill="{INK2}">{e(name)}</text>')
        lx += 20 + 7.4 * len(name) + 28
    for i, (label, dn, mid, up) in enumerate(rows):
        y = top + i * rh + (rh - bh) / 2
        out.append(f'<text x="{left - 12}" y="{y + bh / 2 + 5:.1f}" font-size="14" fill="{INK}" text-anchor="end">{e(label)}</text>')
        x = sx(0)
        for (name, col, tcol), f in zip(names, (dn, mid, up)):
            w = sx(f) - sx(0)
            if w <= 0.5:
                continue
            gap = 2 if x > sx(0) else 0
            out.append(f'<g class="ams-mark"><title>{e(label)}: {e(pct(f))} {e(name)}</title>'
                       f'<rect x="{x + gap:.1f}" y="{y:.1f}" width="{max(w - gap, 0.5):.1f}" height="{bh}" rx="3" fill="{col}"/>')
            txt = pct(f)
            if w - gap > 9 * len(txt) + 10:
                out.append(f'<text x="{x + gap + (w - gap) / 2:.1f}" y="{y + bh / 2 + 5:.1f}" font-size="13" '
                           f'fill="{tcol}" text-anchor="middle" font-weight="600">{e(txt)}</text>')
            out.append("</g>")
            x += w
    out.append("</svg>")
    (SITE_STATIC / "grafieken" / f"{fname}.svg").write_text("\n".join(out) + "\n", encoding="utf-8")


def build_charts(so):
    (SITE_STATIC / "grafieken").mkdir(parents=True, exist_ok=True)
    T = {}
    pt, kw, sd = so["per_type"], so["per_kwintiel"], so["per_stadsdeel"]

    def row(label, s, var="A"):
        return (label, s[f"p_{var}_med"],
                f"{pct(s[f'p_{var}_med'], 1, sign=True)} ({eur(round(s[f'd_{var}_med']), sign=True)})",
                f"{label}: mediane verandering {pct(s[f'p_{var}_med'], 1, sign=True)}, "
                f"{eur(round(s[f'd_{var}_med']), sign=True)} per jaar (nu {eur(round(s['ozb_nu_med']))})")

    rows_type = [row("Alle woningen", so["stad"]), row("Appartementen", pt["appartement"]),
                 row("Grondgebonden woningen", pt["grondgebonden"])]
    svg_diverging_bars(rows_type, "OZB-verandering per woningtype, alleen grond belast",
                       "Mediane verandering van de OZB per woning bij een budgetneutrale verschuiving naar alleen grond.",
                       "ozb-type", [-0.2, -0.1, 0, 0.1, 0.2])
    kwl = {1: "Laagste 20%", 2: "20–40%", 3: "40–60%", 4: "60–80%", 5: "Hoogste 20%"}
    rows_kw = [row(kwl[int(k)], v) for k, v in sorted(kw.items(), key=lambda x: int(x[0]))]
    svg_diverging_bars(rows_kw, "OZB-verandering naar inkomen van de buurt, alleen grond belast",
                       "Mediane verandering per woning, buurten ingedeeld in vijf groepen met elk evenveel woningen, "
                       "van laag naar hoog gemiddeld gestandaardiseerd huishoudinkomen.",
                       "ozb-inkomen", [-0.2, -0.1, 0, 0.1, 0.2])
    order = sorted(sd.items(), key=lambda x: x[1]["p_A_med"])
    rows_sd = [row(k, v) for k, v in order]
    svg_diverging_bars(rows_sd, "OZB-verandering per stadsdeel, alleen grond belast",
                       "Mediane verandering van de OZB per woning per stadsdeel.", "ozb-stadsdeel",
                       [-0.2, -0.1, 0, 0.1, 0.2])
    share_rows = [(lbl, s["aandeel_min10_A"], 1 - s["aandeel_min10_A"] - s["aandeel_plus10_A"], s["aandeel_plus10_A"])
                  for lbl, s in [("Alle woningen", so["stad"]), ("Appartementen", pt["appartement"]),
                                 ("Grondgebonden woningen", pt["grondgebonden"])]
                  + [(f"Inkomen: {kwl[int(k)].lower()}", v) for k, v in sorted(kw.items(), key=lambda x: int(x[0]))]]
    svg_share_bars(share_rows, "Hoeveel woningen gaan er meer dan 10% op voor- of achteruit?",
                   "Aandeel woningen per groep met een OZB-daling of -stijging van meer dan 10%, alleen grond belast.",
                   "ozb-aandeel")

    def trow(label, s):
        return {"groep": label, "woningen": nl(s["woningen"]), "ozb_nu": eur(round(s["ozb_nu_med"])),
                "p_A": pct(s["p_A_med"], 1, sign=True), "d_A": eur(round(s["d_A_med"]), sign=True),
                "p_B": pct(s["p_B_med"], 1, sign=True), "d_B": eur(round(s["d_B_med"]), sign=True),
                "min10_A": pct(s["aandeel_min10_A"]), "plus10_A": pct(s["aandeel_plus10_A"]),
                "min10_B": pct(s["aandeel_min10_B"]), "plus10_B": pct(s["aandeel_plus10_B"])}

    T["ozb_type"] = [trow("Alle woningen", so["stad"]), trow("Appartementen", pt["appartement"]),
                     trow("Grondgebonden woningen", pt["grondgebonden"])]
    T["ozb_inkomen"] = [{**trow(kwl[int(k)], v), "inkomen": f"{eur(v['inkomen_min'])}–{eur(v['inkomen_max'])}"}
                        for k, v in sorted(kw.items(), key=lambda x: int(x[0]))]
    T["ozb_stadsdeel"] = [trow(k, v) for k, v in order]
    return T


# ---------------------------------------------------------------- map layers
def build_layers(land, park, ozb):
    out = SITE_STATIC / "data"
    out.mkdir(parents=True, exist_ok=True)
    b = land.merge(ozb[["buurtcode", "p_A_med", "p_B_med", "d_A_med", "ozb_nu_med"]], on="buurtcode", how="left")
    pk = pd.read_csv(OUT / "buurt_parkeren.csv")[["buurtcode", "terrein_m2", "terrein_waarde_central", "straat_m2"]]
    b = b.merge(pk, on="buurtcode", how="left")
    b = b[b.water != "JA"].copy()
    own = b.bron_grondprijs == "buurt"

    def r(x, n):
        return None if pd.isna(x) else (int(round(x, n)) if n <= 0 else round(float(x), n))

    feats = gpd.GeoDataFrame({
        "c": b.buurtcode, "n": b.buurtnaam, "s": b.stadsdeel, "w": b.woningen_bag.fillna(0).astype(int),
        "b": b.bron_grondprijs,
        "gw": [r(x, -1) if o else None for x, o in zip(b.grondwaarde_m2_wo_central, own)],
        "gwl": [r(x, -1) if o else None for x, o in zip(b.grondwaarde_m2_wo_low, own)],
        "gwh": [r(x, -1) if o else None for x, o in zip(b.grondwaarde_m2_wo_high, own)],
        "gp": [r(x, -1) if o else None for x, o in zip(b.grondprijs_m2_central, own)],
        "gpl": [r(x, -1) if o else None for x, o in zip(b.grondprijs_m2_low, own)],
        "gph": [r(x, -1) if o else None for x, o in zip(b.grondprijs_m2_high, own)],
        "ga": [r(x * 100, 0) if o else None for x, o in zip(b.grondaandeel_central, own)],
        "woz": [r(x, -3) for x in b.woz_gem],
        "dh": [r(x, 1) if o else None for x, o in zip(b.dichtheid, own)],
        "oz": [r(x * 100, 1) for x in b.p_A_med], "oz3": [r(x * 100, 1) for x in b.p_B_med],
        "ozd": [r(x, 0) for x in b.d_A_med], "ozn": [r(x, 0) for x in b.ozb_nu_med],
        "pt": [r(x, -1) for x in b.terrein_m2], "pv": [r(x, -4) for x in b.terrein_waarde_central],
        "geometry": b.geometry.simplify(4).values}, crs=b.crs)
    feats.to_crs("EPSG:4326").to_file(out / "buurten.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    lots = park[park.klasse == "terrein"].copy()
    lots_named = gpd.read_file(OUT / "parkeerterreinen.geojson").to_crs(lots.crs)
    lots_named["rep"] = lots_named.geometry.representative_point()
    poly = gpd.GeoDataFrame({
        "l": lots_named.label, "m": lots_named.opp_onbebouwd_m2.round(-1).astype(int),
        "v": lots_named.waarde_central.round(-5), "vl": lots_named.waarde_low.round(-5),
        "vh": lots_named.waarde_high.round(-5), "b": lots_named.bron_grondprijs,
        "geometry": lots_named.geometry.simplify(1.0)}, crs=lots.crs)
    pts = poly.copy()
    pts["geometry"] = lots_named.rep.values
    both = pd.concat([poly, pts], ignore_index=True)
    gpd.GeoDataFrame(both, crs=lots.crs).to_crs("EPSG:4326").to_file(
        out / "parkeerterreinen.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)

    breaks = {
        "gw": nice_breaks(b.grondwaarde_m2_wo_central[own], b.woningen_bag[own], step=250),
        "gp": nice_breaks(b.grondprijs_m2_central[own], b.woningen_bag[own], step=500),
        "oz": [-25, -10, -3, 3, 10, 25],
    }
    return b, breaks


def copy_downloads():
    out = SITE_STATIC / "data"
    for f in ("buurt_grondprijs.csv", "buurt_parkeren.csv", "top20_parkeerterreinen.csv", "ozb_buurt.csv",
              "ozb_buurt_type.csv"):
        shutil.copy(OUT / f, out / f)


# ---------------------------------------------------------------- static maps
def classify(values, breaks):
    return np.digitize(values, breaks)


def map_png(b, column, breaks, colors, title, legend_fmt, fname, nodata_label, parking=None, size=(10, 8.6)):
    fig, ax = plt.subplots(figsize=size, dpi=120)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    has = b[column].notna()
    b[~has].plot(ax=ax, color=NODATA, edgecolor="#d9d6cf", linewidth=0.3, hatch="////")
    cls = classify(b.loc[has, column].values, breaks)
    b[has].plot(ax=ax, color=[colors[c] for c in cls], edgecolor="#ffffff", linewidth=0.25)
    if parking is not None:
        parking.plot(ax=ax, color=NAVY, edgecolor=NAVY, linewidth=0.6)
    ax.set_axis_off()
    labels = []
    edges = [None, *breaks, None]
    for i in range(len(colors)):
        lo_, hi_ = edges[i], edges[i + 1]
        labels.append(legend_fmt(lo_, hi_))
    handles = [Patch(facecolor=c, edgecolor="none", label=lab) for c, lab in zip(colors, labels)]
    handles.append(Patch(facecolor=NODATA, edgecolor="#d9d6cf", hatch="////", label=nodata_label))
    if parking is not None:
        handles.append(Patch(facecolor=NAVY, edgecolor=NAVY, label="Parkeerterrein (bovengronds)"))
    leg = ax.legend(handles=handles, loc="lower left", frameon=True, fontsize=9, title=None, borderpad=0.8)
    leg.get_frame().set_facecolor("#ffffff")
    leg.get_frame().set_edgecolor(BORDER)
    fig.text(0.03, 0.965, title, fontsize=14, color=NAVY, weight="bold", va="top")
    fig.text(0.03, 0.93, "Schatting, geen officiële waarde. Peildatum WOZ 1-1-2024.", fontsize=9.5, color=INK2, va="top")
    fig.text(0.03, 0.02, "Bron: CBS, Kadaster/PDOK (CC BY 4.0), BAG, BGT; OpenStreetMap (ODbL). "
             "Bewerking: wonenisteduur.nl", fontsize=8, color=MUTED)
    plt.subplots_adjust(left=0.01, right=0.99, top=0.9, bottom=0.04)
    fig.savefig(SITE_STATIC / fname, dpi=120, facecolor=BG)
    plt.close(fig)


def build_maps(b, breaks, park):
    rd = b.copy()

    def fmt_eur(lo_, hi_):
        if lo_ is None:
            return f"minder dan €{nl(hi_)}"
        if hi_ is None:
            return f"€{nl(lo_)} of meer"
        return f"€{nl(lo_)} – €{nl(hi_)}"

    def fmt_pct(lo_, hi_):
        if lo_ is None:
            return f"meer dan {nl(-hi_)}% minder"
        if hi_ is None:
            return f"meer dan {nl(lo_)}% meer"
        if lo_ < 0 < hi_:
            return f"−{nl(-lo_)}% tot +{nl(hi_)}%"
        if hi_ <= 0:
            return f"{nl(-hi_)}–{nl(-lo_)}% minder"
        return f"{nl(lo_)}–{nl(hi_)}% meer"

    rd["gwv"] = rd.grondwaarde_m2_wo_central.where(rd.bron_grondprijs == "buurt")
    map_png(rd, "gwv", breaks["gw"], SEQ, "Grondwaarde per m² woonoppervlak, per buurt", fmt_eur,
            "kaart-grondwaarde.png", "geen eigen schatting (weinig woningen)")
    rd["ozv"] = rd.p_A_med * 100
    map_png(rd, "ozv", breaks["oz"], DIV, "OZB-verandering typische woning, alleen grond belast", fmt_pct,
            "kaart-ozb.png", "niet berekend")
    lots = park[park.klasse == "terrein"]
    rd["gwl"] = rd.gwv
    map_png(rd, "gwl", breaks["gw"], SEQ, "Bovengrondse parkeerterreinen op grondwaarde", fmt_eur,
            "kaart-parkeren.png", "geen eigen schatting (weinig woningen)", parking=lots)
    # Social image 1200x630 from the land map.
    fig, ax = plt.subplots(figsize=(10, 5.25), dpi=120)
    fig.patch.set_facecolor(BG)
    has = rd.gwv.notna()
    rd[~has].plot(ax=ax, color=NODATA, edgecolor="#d9d6cf", linewidth=0.3)
    rd[has].plot(ax=ax, color=[SEQ[c] for c in classify(rd.gwv[has].values, breaks["gw"])], edgecolor="#fff",
                 linewidth=0.2)
    ax.set_axis_off()
    ax.set_xlim(rd.total_bounds[0] + 1500, rd.total_bounds[2] - 3000)
    fig.text(0.03, 0.93, "Waar zit de grondwaarde in Amsterdam?", fontsize=20, color=NAVY, weight="bold", va="top")
    fig.text(0.03, 0.84, "Schatting per buurt · wonenisteduur.nl/amsterdam", fontsize=12, color=INK2, va="top")
    plt.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.0)
    fig.savefig(SITE_STATIC / "kaart-og.png", dpi=120, facecolor=BG)
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    ensure_dirs()
    sl, sp, so = (read_json(WORK / f"summary_{k}.json") for k in ("land", "parking", "ozb"))
    land = gpd.read_parquet(WORK / "buurt_land.parquet")
    park = gpd.read_parquet(WORK / "parking_pieces.parquet")
    ozb = pd.read_parquet(WORK / "ozb_buurt.parquet")

    C = build_numbers(sl, sp, so, land)
    T = build_charts(so)
    T["top20"] = [{"rang": r["rang"], "label": r["label"], "stadsdeel": r["stadsdeel"], "m2": nl(r["m2"]),
                   "waarde": nl(r["waarde_central"] / 1e6),
                   "bereik": f"{nl(r['waarde_low'] / 1e6)}–{nl(r['waarde_high'] / 1e6)}"}
                  for r in sp["top20"]]
    b, breaks = build_layers(land, park, ozb)
    T["stadsdeel_grond"] = []
    own = b[b.bron_grondprijs == "buurt"]
    for sd, g in own.groupby("stadsdeel"):
        w = g.woningen_bag
        T["stadsdeel_grond"].append({
            "stadsdeel": sd, "buurten": len(g), "woningen": nl(w.sum()),
            "grondaandeel": pct(np.average(g.grondaandeel_central, weights=g.woz_som)),
            "gw": eur(round(np.average(g.grondwaarde_m2_wo_central, weights=w), -1)),
            "gp": eur(round(np.average(g.grondprijs_m2_central, weights=w), -2)),
            "pk_ha": nl(g.terrein_m2.sum() / 1e4, 1), "pk_mln": nl(g.terrein_waarde_central.sum() / 1e6)})
    copy_downloads()
    build_maps(b, breaks, park)
    write_json(SITE_DATA / "cijfers.json", C, indent=1)
    write_json(SITE_DATA / "tabellen.json", T, indent=1)
    write_json(SITE_DATA / "kaart.json", {"breaks": breaks, "seq": SEQ, "div": DIV, "nodata": NODATA,
                                          "navy": NAVY}, indent=1)
    sizes = {p.name: p.stat().st_size for p in (SITE_STATIC / "data").glob("*")}
    log("static data sizes", sizes, "total", sum(sizes.values()))
    log("breaks", breaks)


if __name__ == "__main__":
    main()
