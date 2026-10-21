# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio>=0.9", "pyarrow>=15", "shapely>=2.0", "pandas>=2.2", "numpy>=1.26"]
# ///
"""Deliverable A: estimated land price (EUR per m2 of land) per buurt.

Doucet's "simplest viable method", adapted to Dutch open data:

  1. Residual land share per buurt
        a_raw = (WOZ - depreciated rebuild cost) / WOZ
     with WOZ = CBS average WOZ x BAG dwellings, and the rebuild cost summed
     over the buurt's dwellings (BAG floor area x cost per m2 x age factor).
  2. Shrink toward the city baseline: a = w a_raw + (1 - w) a_city,
     w = n / (n + k), n = dwellings.
  3. Land per dwelling from the Kadastrale kaart: each parcel's area is split
     over the panden on it (by footprint overlap) and each pand's share over its
     verblijfsobjecten (by floor area).
  4. Land rate r = land value per dwelling / land area per dwelling
             = a x mean WOZ / mean land m2 per dwelling.

Three variants (low / central / high land price) combine the rebuild-cost and
depreciation ranges in params.toml. If official grondstaffels are available
(input/grondstaffels.*), they replace the estimate; see README.

    uv run 03_land.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from common import HERE, OUT, RAW, WORK, ensure_dirs, log, params, read_json, write_json

P = params()
STADSDEEL = {"A": "Centrum", "B": "Westpoort", "E": "West", "F": "Nieuw-West", "K": "Zuid", "M": "Oost",
             "N": "Noord", "S": "Weesp", "T": "Zuidoost", "9": "Water"}
VARIANTS = ("low", "central", "high")


# ---------------------------------------------------------------- inputs
def cbs_buurt_table() -> pd.DataFrame:
    d = read_json(RAW / "cbs" / f"{P['area']['cbs_kerncijfers']}_ams.json")
    rows = []
    for r in d["rows"]:
        code = r["WijkenEnBuurten"].strip()
        rows.append({
            "code": code,
            "woningvoorraad_cbs": r.get("Woningvoorraad_35"),
            "woz_gem": None if r.get("GemiddeldeWOZWaardeVanWoningen_39") is None
            else r["GemiddeldeWOZWaardeVanWoningen_39"] * 1000.0,
            "pct_eengezins_cbs": r.get("PercentageEengezinswoning_40"),
            "pct_koop_cbs": r.get("Koopwoningen_47"),
            "pct_corporatie_cbs": r.get("InBezitWoningcorporatie_49"),
            "inkomen_gem": None if r.get("GemGestandaardiseerdInkomen_83") is None
            else r["GemGestandaardiseerdInkomen_83"] * 1000.0,
            "pct_laag_inkomen": r.get("k_40HuishoudensMetLaagsteInkomen_84"),
        })
    return pd.DataFrame(rows).set_index("code")


def rebuild_cost_per_m2() -> dict:
    rc = P["rebuild_cost"]
    rows = read_json(RAW / "cbs" / "83673NED.json")["rows"]
    per = f"{rc['cbs_year']}VJ12"
    vals = [r["GemiddeldeBouwkostenPerM_3"] for r in rows
            if r["RegioS"].strip() == rc["cbs_region"] and r["Perioden"] == per]
    if len(vals) != 2:
        raise SystemExit(f"expected huur+koop rows for {rc['cbs_region']} {per}, got {vals}")
    base = float(np.mean(vals))
    # Land price "low" goes with the high rebuild cost, and vice versa.
    cost = {
        "low": base * rc["btw"] * rc["bijkomend"]["high"] * rc["premium"]["high"],
        "central": base * rc["btw"] * rc["bijkomend"]["central"] * rc["premium"]["central"],
        "high": base * rc["btw"] * rc["bijkomend"]["low"] * rc["premium"]["low"],
    }
    return {"base_excl_btw": base, "base_values": vals, "period": per, "region": rc["cbs_region"], **cost}


def depreciation(age: np.ndarray, variant: str) -> np.ndarray:
    d = P["depreciation"]
    key = {"low": "low_land", "central": "central", "high": "high_land"}[variant]
    return np.maximum(d["floor"][key], 1.0 - age / d["life"][key])


def national_land_share() -> dict:
    rows = read_json(RAW / "cbs" / "84550NED.json")["rows"]
    by = {}
    for r in rows:
        by.setdefault(r["Perioden"], {})[r["TypeNietFinancieleActiva"]] = r["Eindbalans_6"]
    yr = max(k for k, v in by.items() if v.get("A047182") and v.get("A047162"))
    land, bldg = by[yr]["A047182"], by[yr]["A047162"]
    return {"year": yr[:4], "land_mln": land, "woningen_mln": bldg, "share": land / (land + bldg)}


def national_check(cost: dict) -> dict:
    """Apply the same rebuild-cost and depreciation rules to every Dutch dwelling.

    Returns national WOZ and depreciated rebuild cost totals per variant. The
    implied national land share can be compared with (or calibrated to) CBS's
    own estimate for land under dwellings (84550NED).
    """
    import pyogrio

    la = P["land_area"]
    df = pyogrio.read_dataframe(RAW / "bag" / "bag-light.gpkg", layer="verblijfsobject", read_geometry=False,
                                columns=["oppervlakte", "status", "gebruiksdoel", "bouwjaar"], use_arrow=True)
    df = df[df.status.isin(la["vbo_status"]) & df.gebruiksdoel.fillna("").str.contains("woonfunctie")]
    opp = df.oppervlakte.where(df.oppervlakte.between(la["min_vbo_m2"], la["max_vbo_m2"]))
    opp = opp.fillna(opp.median()).values
    peil = P["area"]["woz_peiljaar"]
    age = np.clip(peil - df.bouwjaar.where(df.bouwjaar.between(1200, peil)).fillna(1975), 0, None).values
    nl = next(r for r in read_json(RAW / "cbs" / f"{P['area']['cbs_kerncijfers']}_ams.json")["rows"]
              if r["WijkenEnBuurten"].strip() == "NL00")
    woz_gem = nl["GemiddeldeWOZWaardeVanWoningen_39"] * 1000.0
    res = {"dwellings": int(len(df)), "woz_gem": woz_gem, "opp_gem": float(opp.mean()),
           "woz_som": woz_gem * len(df)}
    for v in VARIANTS:
        res[f"drc_per_eur_{v}"] = float((opp * depreciation(age, v)).sum())  # x cost per m2
    return res


def calibrate(cost: dict, nat_check: dict, nat: dict) -> dict:
    """Scale the central rebuild cost so the national land share equals CBS's."""
    for v in VARIANTS:
        nat_check[f"share_{v}_uncalibrated"] = 1 - cost[v] * nat_check[f"drc_per_eur_{v}"] / nat_check["woz_som"]
    if P["rebuild_cost"].get("calibrate_central_to_cbs"):
        target = (1 - nat["share"]) * nat_check["woz_som"] / nat_check["drc_per_eur_central"]
        cost["central_uncalibrated"] = cost["central"]
        cost["calibration_factor"] = target / cost["central"]
        cost["central"] = target
    for v in VARIANTS:
        nat_check[f"share_{v}"] = 1 - cost[v] * nat_check[f"drc_per_eur_{v}"] / nat_check["woz_som"]
    return cost


# ---------------------------------------------------------------- dwellings
def load_dwellings(buurten: gpd.GeoDataFrame) -> pd.DataFrame:
    la = P["land_area"]
    vbo = gpd.read_parquet(WORK / "vbo.parquet")
    # Pand composition, counted over all VBOs in use (woon and niet-woon).
    vbo["opp"] = vbo.oppervlakte.where(vbo.oppervlakte.between(la["min_vbo_m2"], la["max_vbo_m2"]))
    vbo["opp"] = vbo.opp.fillna(vbo.groupby("buurtcode").opp.transform("median")).fillna(vbo.opp.median())
    pand = vbo.groupby("pand_identificatie").agg(n_vbo=("identificatie", "size"), n_woon=("woon", "sum"),
                                                 opp_pand=("opp", "sum"))
    vbo = vbo.join(pand, on="pand_identificatie")
    peil = P["area"]["woz_peiljaar"]
    bj = vbo.bouwjaar.where(vbo.bouwjaar.between(1200, peil))
    bj = bj.fillna(vbo.assign(bj=bj).groupby("buurtcode").bj.transform("median")).fillna(1960)
    vbo["bouwjaar_c"] = bj
    vbo["age"] = np.clip(peil - bj, 0, None)
    ht = P["house_type"]
    vbo["type"] = np.where((vbo.n_woon == 1) & (vbo.n_vbo <= ht["max_vbo_in_pand"]), "grondgebonden", "appartement")
    return vbo


def allocate_land(vbo: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Land area (m2) per VBO following the allocation rule in params.toml."""
    la = P["land_area"]
    panden = gpd.read_parquet(WORK / "panden.parquet")
    panden = panden[panden.identificatie.isin(vbo.pand_identificatie.unique())].reset_index(drop=True)
    perc = gpd.read_parquet(WORK / "percelen.parquet").reset_index(drop=True)
    perc["area"] = perc.kadastrale_grootte.where(perc.kadastrale_grootte > 0, perc.geometry.area)

    pi, ji = perc.sindex.query(panden.geometry, predicate="intersects")
    inter = shapely.area(shapely.intersection(panden.geometry.values[pi], perc.geometry.values[ji]))
    pairs = pd.DataFrame({"pand": panden.identificatie.values[pi], "perc": ji, "overlap": inter})
    pairs = pairs[pairs.overlap > 0.5]
    tot = pairs.groupby("perc").overlap.sum()
    area = perc.area.reindex(tot.index)
    cap = (area > la["cap_min_parcel_m2"]) & (area > la["cap_footprint_multiple"] * tot)
    alloc_area = np.where(cap, la["cap_footprint_multiple"] * tot, area)
    alloc = pd.Series(alloc_area, index=tot.index)
    pairs["land"] = alloc.reindex(pairs.perc).values * pairs.overlap / tot.reindex(pairs.perc).values
    land_pand = pairs.groupby("pand").land.sum()
    land_vbo = land_pand.reindex(vbo.pand_identificatie).values * vbo.opp.values / vbo.opp_pand.values
    used = perc.loc[tot.index]
    stats = {
        "percelen_totaal": int(len(perc)),
        "percelen_met_pand": int(len(tot)),
        "percelen_afgetopt": int(cap.sum()),
        "m2_percelen_met_pand": float(area.sum()),
        "m2_toegedeeld": float(alloc.sum()),
        "m2_afgetopt_weg": float((area - alloc).sum()),
        "m2_percelen_zonder_pand": float(perc.area.sum() - area.sum()),
        "perc_ids_used": int(len(used)),
    }
    return pd.Series(land_vbo, index=vbo.index), stats


# ---------------------------------------------------------------- grondstaffels hook
def official_rates(buurten: gpd.GeoDataFrame, res_land: pd.DataFrame) -> pd.DataFrame | None:
    """If the Woo grondstaffels are present, return EUR/m2 per buurt from them.

    Expected input (see README): input/grondstaffels.gpkg (or .geojson) with one
    polygon per waardegebied and a numeric field `grondprijs_m2` (woningen),
    plus `peildatum`. Rates are mapped to buurten as the residential-land-
    weighted mean over the waardegebieden that overlap each buurt.
    """
    for ext in ("gpkg", "geojson"):
        f = HERE / "input" / f"grondstaffels.{ext}"
        if f.exists():
            gs = gpd.read_file(f).to_crs(buurten.crs)
            ov = gpd.overlay(buurten[["buurtcode", "geometry"]], gs[["grondprijs_m2", "geometry"]], how="intersection")
            ov["w"] = ov.geometry.area
            r = ov.groupby("buurtcode").apply(lambda g: np.average(g.grondprijs_m2, weights=g.w))
            log("official grondstaffels used:", f.name, len(r), "buurten")
            return pd.DataFrame({"r_official": r})
    return None


# ---------------------------------------------------------------- uniformity
def uniformity(buurten: gpd.GeoDataFrame, vbo: pd.DataFrame) -> pd.DataFrame:
    """Spread of WOZ per m2 floor area across CBS 100 m cells within each buurt."""
    f = WORK / "grid.parquet"
    if not f.exists():
        return pd.DataFrame()
    grid = gpd.read_parquet(f)
    grid = grid[grid.woz.notna() & (grid.woz > 0)].copy()
    woon = gpd.GeoDataFrame(vbo[vbo.woon][["opp", "geometry"]], geometry="geometry", crs=buurten.crs)
    j = gpd.sjoin(woon, grid[["cell", "geometry"]], predicate="within")
    opp = j.groupby("cell").opp.agg(["mean", "size"])
    grid = grid.join(opp, on="cell")
    grid = grid[grid["size"] >= 10]
    grid["woz_m2"] = grid.woz * 1000 / grid["mean"]
    cent = grid.copy()
    cent["geometry"] = grid.geometry.centroid
    cent = gpd.sjoin(cent, buurten[["buurtcode", "geometry"]], predicate="within")

    def cv(g):
        w = g["size"].values
        m = np.average(g.woz_m2, weights=w)
        sd = np.sqrt(np.average((g.woz_m2 - m) ** 2, weights=w))
        return pd.Series({"cv_woz_m2": sd / m if len(g) >= 3 else np.nan, "n_cellen": len(g)})

    return cent.groupby("buurtcode").apply(cv, include_groups=False)


def wmedian(values, weights) -> float:
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    m = ~(np.isnan(v) | np.isnan(w))
    v, w = v[m], w[m]
    o = np.argsort(v)
    c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, 0.5 * c[-1])])


# ---------------------------------------------------------------- main
def main():
    ensure_dirs()
    ls = P["land_share"]
    buurten = gpd.read_parquet(WORK / "buurten.parquet")
    buurten["stadsdeel"] = buurten.wijkcode.str[6].map(STADSDEEL)
    cbs = cbs_buurt_table()
    cost = rebuild_cost_per_m2()
    nat = national_land_share()
    nat_check = national_check(cost)
    cost = calibrate(cost, nat_check, nat)
    log("national check", nat_check, "CBS", nat)
    log("rebuild cost EUR/m2", {k: round(v) for k, v in cost.items() if k in VARIANTS}, "base", cost["base_excl_btw"])

    vbo = load_dwellings(buurten)
    vbo["land_m2"], alloc_stats = allocate_land(vbo)
    log("allocation", alloc_stats)
    w = vbo[vbo.woon].copy()
    for v in VARIANTS:
        w[f"drc_{v}"] = w.opp * cost[v] * depreciation(w.age.values, v)
    w["herbouw_nieuw"] = w.opp * cost["central"]  # undepreciated, for the BSQ check

    g = w.groupby("buurtcode")
    b = pd.DataFrame({
        "woningen_bag": g.size(),
        "opp_gem": g.opp.mean(),
        "bouwjaar_med": g.bouwjaar_c.median(),
        "pct_grondgebonden_bag": g.type.apply(lambda s: 100 * (s == "grondgebonden").mean()),
        "woningen_met_grond": g.land_m2.count(),
        "grond_m2_per_woning": g.land_m2.mean(),
        "herbouw_nieuw_som": g.herbouw_nieuw.sum(),
        **{f"drc_{v}_som": g[f"drc_{v}"].sum() for v in VARIANTS},
    })
    b = b.join(cbs, how="left")
    b["grond_m2_som"] = g.land_m2.sum()
    b["woz_som"] = b.woz_gem * b.woningen_bag
    b["woz_m2"] = b.woz_gem / b.opp_gem
    has_woz = b.woz_gem.notna() & (b.woningen_bag > 0)
    # CBS averages far below the city level per m2 usually mean special stock
    # (student or temporary units valued as a complex, or new builds after the
    # peildatum). Those buurten get no own residual estimate.
    med_m2 = wmedian(b.woz_m2[has_woz], b.woningen_bag[has_woz])
    b["woz_afwijkend"] = has_woz & (b.woz_m2 < ls["min_woz_m2_frac"] * med_m2)
    ok = has_woz & ~b.woz_afwijkend
    own = ok & (b.woningen_bag >= ls["min_dwellings"]) & (b.grond_m2_per_woning > 0)
    b["wijkcode"] = buurten.set_index("buurtcode").wijkcode.reindex(b.index)
    wk = b[own].groupby("wijkcode")
    out = {"woz_m2_median_woning": med_m2}
    for v in VARIANTS:
        a_raw = ((b.woz_som - b[f"drc_{v}_som"]) / b.woz_som).clip(ls["clip_min"], ls["clip_max"])
        a_city = float((b.woz_som[ok].sum() - b[f"drc_{v}_som"][ok].sum()) / b.woz_som[ok].sum())
        wgt = b.woningen_bag / (b.woningen_bag + ls["shrink_k"])
        a = wgt * a_raw + (1 - wgt) * a_city
        b[f"grondaandeel_ruw_{v}"] = a_raw.where(ok)
        b[f"grondaandeel_{v}"] = a.where(ok)
        r_own = a * b.woz_gem / b.grond_m2_per_woning
        # Pooled wijk rate (over buurten with an own estimate) for the others.
        woz = wk.woz_som.sum()
        a_w = ((woz - wk[f"drc_{v}_som"].sum()) / woz).clip(ls["clip_min"], ls["clip_max"])
        r_w = a_w * (woz / wk.woningen_bag.sum()) / (wk.grond_m2_som.sum() / wk.woningen_met_grond.sum())
        b[f"grondprijs_m2_{v}"] = r_own.where(own, b.wijkcode.map(r_w))
        out[f"a_city_{v}"] = a_city
    b["gewicht"] = b.woningen_bag / (b.woningen_bag + ls["shrink_k"])
    b["bsq_check"] = ((b.woz_som - b.herbouw_nieuw_som * 1.05) / b.woz_som).clip(0.05, 0.49).where(ok)
    b["bron_grondprijs"] = np.where(own, "buurt", np.where(b.grondprijs_m2_central.notna(), "wijk", "geen"))
    b["woz_bruikbaar"] = ok

    off = official_rates(buurten, b)
    if off is not None:
        b = b.join(off)
        for v in VARIANTS:
            b[f"grondprijs_m2_{v}"] = b.r_official.fillna(b[f"grondprijs_m2_{v}"])
        b["bron_grondprijs"] = np.where(b.r_official.notna(), "grondstaffel", b.bron_grondprijs)

    b["grondwaarde_per_woning_central"] = b.grondprijs_m2_central * b.grond_m2_per_woning
    b = b.join(uniformity(buurten, vbo))

    gdf = buurten.merge(b.drop(columns="wijkcode"), left_on="buurtcode", right_index=True, how="left")
    gdf.to_parquet(WORK / "buurt_land.parquet")
    keep_w = ["buurtcode", "type", "opp", "age", "land_m2", "drc_central", "drc_low", "drc_high"]
    w[keep_w].to_parquet(WORK / "dwellings.parquet")

    # ------------------------------------------------------------ summary
    res = gdf[gdf.bron_grondprijs.isin(["buurt", "wijk", "grondstaffel"])]
    tot_woz = float(gdf.woz_som.sum())
    summ = {
        "rebuild_cost": cost,
        "allocation": alloc_stats,
        "national_land_share": nat,
        "national_check": nat_check,
        "dwellings_bag": int(len(w)),
        "dwellings_with_land": int(w.land_m2.notna().sum()),
        "dwellings_cbs_gemeente": cbs.loc[P["area"]["gemeentecode"], "woningvoorraad_cbs"],
        "woz_gem_gemeente": cbs.loc[P["area"]["gemeentecode"], "woz_gem"],
        "buurten": int(len(gdf)),
        "buurten_eigen_schatting": int((gdf.bron_grondprijs == "buurt").sum()),
        "buurten_wijk": int((gdf.bron_grondprijs == "wijk").sum()),
        "buurten_geen": int((gdf.bron_grondprijs == "geen").sum()),
        "woz_som": tot_woz,
        **out,
    }
    for v in VARIANTS:
        lv = (gdf[f"grondprijs_m2_{v}"] * gdf.grond_m2_per_woning * gdf.woningen_met_grond).sum()
        summ[f"grondwaarde_woningen_{v}"] = float(lv)
        summ[f"grondprijs_m2_median_woning_{v}"] = wmedian(res[f"grondprijs_m2_{v}"], res.woningen_bag)
        summ[f"grondaandeel_gem_{v}"] = float(np.average(res[f"grondaandeel_{v}"].dropna(),
                                                         weights=res.loc[res[f"grondaandeel_{v}"].notna(), "woz_som"]))
    summ["bsq_check_gem"] = float(np.average(gdf.bsq_check.dropna(), weights=gdf.woz_som[gdf.bsq_check.notna()]))
    summ["bsq_cap_binds_share_buurten"] = float((gdf.bsq_check >= 0.49).sum() / gdf.bsq_check.notna().sum())
    summ["cv_woz_m2_median"] = float(gdf.cv_woz_m2.median())
    summ["cv_woz_m2_share_gt_025"] = float((gdf.cv_woz_m2 > 0.25).sum() / gdf.cv_woz_m2.notna().sum())
    summ["cv_buurten"] = int(gdf.cv_woz_m2.notna().sum())
    write_json(WORK / "summary_land.json", summ, indent=1)
    log("summary", {k: v for k, v in summ.items() if not isinstance(v, dict)})

    # ------------------------------------------------------------ deliverable files
    cols = ["buurtcode", "buurtnaam", "wijkcode", "wijknaam", "stadsdeel", "woningen_bag", "woningvoorraad_cbs",
            "woz_gem", "opp_gem", "woz_m2", "bouwjaar_med", "pct_grondgebonden_bag", "pct_eengezins_cbs",
            "grond_m2_per_woning", "gewicht",
            *[f"grondaandeel_ruw_{v}" for v in VARIANTS], *[f"grondaandeel_{v}" for v in VARIANTS],
            *[f"grondprijs_m2_{v}" for v in VARIANTS], "bron_grondprijs", "grondwaarde_per_woning_central",
            "bsq_check", "cv_woz_m2", "n_cellen", "inkomen_gem", "pct_koop_cbs", "pct_corporatie_cbs"]
    tab = gdf[cols].copy()
    for c in tab.columns:
        if tab[c].dtype.kind == "f":
            tab[c] = tab[c].round(3 if c.startswith(("grondaandeel", "gewicht", "bsq", "cv_")) else 0)
    tab.to_csv(OUT / "buurt_grondprijs.csv", index=False)
    geo = gdf[cols + ["geometry"]].copy()
    for c in cols:
        geo[c] = tab[c]
    geo["geometry"] = geo.geometry.simplify(1.0)
    geo.to_crs("EPSG:4326").to_file(OUT / "buurt_grondprijs.geojson", driver="GeoJSON",
                                    COORDINATE_PRECISION=6)
    log("wrote", OUT / "buurt_grondprijs.csv")


if __name__ == "__main__":
    main()
