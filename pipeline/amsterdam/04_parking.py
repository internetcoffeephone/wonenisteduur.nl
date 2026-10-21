# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyarrow>=15", "shapely>=2.0", "pandas>=2.2", "numpy>=1.26"]
# ///
"""Deliverable B: land value under surface parking.

  1. Candidates: BGT wegdeel `parkeervlak` at ground level (relatieve
     hoogteligging 0) plus OSM amenity=parking polygons that are not decks,
     garages, underground or street-side parking.
  2. Merge touching polygons; each merged piece is classified as
       - straat      on-street bays: < min_lot_m2, or a thin strip
                     (2A/P < strip_max_width_m and P^2/4A > strip_min_elongation),
                     or a narrow piece running along a BGT rijbaan
       - gebouwd     covered >= structure_overlap by BAG panden (deck/garage)
       - terrein     everything else: an off-street surface lot
  3. Value = surface area (minus any building on it) x the buurt's land value
     per m2 floor area x the city's typical residential density (m2 floor area
     per m2 residential land), split over buurten where a lot crosses a boundary.

Ownership is unknown: nothing here links a lot to its owner. Lots are named
by type and location only.

    uv run 04_parking.py
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from common import OUT, WORK, ensure_dirs, log, params, write_json

P = params()
K = P["parking"]
VARIANTS = ("low", "central", "high")


def candidates() -> gpd.GeoDataFrame:
    wd = gpd.read_parquet(WORK / "bgt_wegdeel.parquet")
    bgt = wd[(wd.functie == "parkeervlak") & (wd.hoogte == 0)][["geometry"]].assign(bron="bgt")
    osm = gpd.read_parquet(WORK / "osm_parking.parquet")
    lay = pd.to_numeric(osm.layer, errors="coerce").fillna(0)
    keep = (~osm.parking.isin(K["osm_exclude_parking"]) & (osm.building == "") & (lay == 0)
            & ~osm.location.isin(["underground", "rooftop", "roof"]))
    log("osm parking kept", int(keep.sum()), "of", len(osm))
    o = osm[keep][["geometry", "park_ride", "name", "access"]].assign(bron="osm")
    return pd.concat([bgt, o], ignore_index=True), osm[keep], wd[wd.functie.str.startswith("rijbaan")]


def merge_pieces(cand: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    b = K["merge_buffer_m"]
    geoms = shapely.make_valid(cand.geometry.values)
    merged = shapely.union_all(shapely.buffer(geoms, b, join_style="mitre"))
    merged = shapely.buffer(merged, -b, join_style="mitre")
    parts = shapely.get_parts(merged)
    parts = parts[shapely.area(parts) > 1]
    pieces = gpd.GeoDataFrame({"geometry": parts}, crs=cand.crs)
    # Provenance: which sources make up each piece.
    j = gpd.sjoin(cand[["bron", "geometry"]], pieces, predicate="intersects")
    src = j.groupby("index_right").bron.agg(lambda s: "+".join(sorted(set(s))))
    pieces["bron"] = src.reindex(pieces.index).fillna("bgt")
    return pieces


def classify(pieces: gpd.GeoDataFrame, rijbaan: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    a = pieces.geometry.area
    per = pieces.geometry.length
    pieces["opp_m2"] = a
    pieces["breedte_m"] = 2 * a / per
    pieces["rek"] = per ** 2 / (4 * a)
    # Share of the outline that runs along a carriageway.
    rb = rijbaan[rijbaan.intersects(shapely.box(*pieces.total_bounds))]
    rb_union = shapely.union_all(shapely.buffer(rb.geometry.values, 1.0))
    big = pieces.index[a >= K["min_lot_m2"]]
    touch = pd.Series(0.0, index=pieces.index)
    bnd = pieces.loc[big].geometry.boundary
    touch.loc[big] = shapely.length(shapely.intersection(bnd.values, rb_union)) / shapely.length(bnd.values)
    pieces["langs_rijbaan"] = touch
    strip = (pieces.breedte_m < K["strip_max_width_m"]) & (pieces.rek > K["strip_min_elongation"])
    along = (touch >= K["carriageway_touch_frac"]) & (pieces.breedte_m < 2 * K["strip_max_width_m"])
    pieces["klasse"] = np.where((a < K["min_lot_m2"]) | strip | along, "straat", "terrein")

    # Decks and garages: share covered by BAG panden.
    panden = gpd.read_parquet(WORK / "panden.parquet")
    lots = pieces.index[pieces.klasse == "terrein"]
    li, pi = panden.sindex.query(pieces.loc[lots].geometry.values, predicate="intersects")
    cov = pd.Series(0.0, index=pieces.index)
    if len(li):
        inter = shapely.area(shapely.intersection(pieces.loc[lots].geometry.values[li], panden.geometry.values[pi]))
        s = pd.Series(inter).groupby(li).sum()
        cov.loc[lots[s.index]] = s.values / pieces.loc[lots[s.index]].opp_m2.values
    pieces["bebouwd_aandeel"] = cov.clip(0, 1)
    pieces.loc[(pieces.klasse == "terrein") & (pieces.bebouwd_aandeel >= K["structure_overlap"]), "klasse"] = "gebouwd"
    pieces["opp_onbebouwd_m2"] = pieces.opp_m2 * (1 - pieces.bebouwd_aandeel)
    return pieces


def value(pieces: gpd.GeoDataFrame, buurten: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    # Lots are valued at the buurt's location value applied at the city's typical
    # residential density (grondprijs_m2_std), not at the buurt's own parcel
    # density, so dense tower parcels do not inflate the value of a car park.
    cols = ["buurtcode", "buurtnaam", "stadsdeel", "bron_grondprijs", *[f"grondprijs_m2_std_{v}" for v in VARIANTS],
            "geometry"]
    pieces = pieces.reset_index(names="lot")
    ov = gpd.overlay(pieces[["lot", "klasse", "bebouwd_aandeel", "geometry"]], buurten[cols], how="intersection",
                     keep_geom_type=True)
    ov["m2"] = ov.geometry.area * (1 - ov.bebouwd_aandeel)
    for v in VARIANTS:
        ov[f"waarde_{v}"] = ov.m2 * ov[f"grondprijs_m2_std_{v}"]
    # Main buurt (largest share) and rate source per lot.
    main = ov.sort_values("m2", ascending=False).drop_duplicates("lot").set_index("lot")
    pieces = pieces.set_index("lot")
    for c in ("buurtcode", "buurtnaam", "stadsdeel", "bron_grondprijs"):
        pieces[c] = main[c]
    own = ov[ov.bron_grondprijs == "buurt"]
    for v in VARIANTS:
        pieces[f"waarde_{v}"] = own.groupby("lot")[f"waarde_{v}"].sum().reindex(pieces.index).fillna(0.0)
        pieces[f"waarde_indicatief_{v}"] = ov[ov.bron_grondprijs == "wijk"].groupby("lot")[f"waarde_{v}"].sum() \
            .reindex(pieces.index).fillna(0.0)
    pieces["m2_gewaardeerd"] = own.groupby("lot").m2.sum().reindex(pieces.index).fillna(0.0)
    return pieces, ov


def name_lots(lots: gpd.GeoDataFrame, osm_kept: gpd.GeoDataFrame) -> pd.DataFrame:
    """Descriptive names by type and location; never by owner, operator or brand.

    Only public landmarks (stations, winkelcentra, stadions) are named. Near a
    hospital, school, supermarket or furniture store the type is given without
    a name, because that name could point at the likely owner.
    """
    places = gpd.read_parquet(WORK / "osm_places.parquet")
    vbo = gpd.read_parquet(WORK / "vbo.parquet")[["openbare_ruimte_naam", "geometry"]]
    order = [("station", 300, "bij station {}"), ("winkelcentrum", 250, "bij winkelcentrum {}"),
             ("stadion", 400, "bij {}"), ("ziekenhuis", 300, "bij een ziekenhuis"),
             ("onderwijsinstelling", 250, "bij een onderwijsinstelling"), ("woonwinkel", 120, "bij woonwinkels"),
             ("winkelgebied", 150, "bij een winkelgebied"), ("supermarkt", 80, "bij een supermarkt")]
    pr = gpd.sjoin(osm_kept[osm_kept.park_ride.isin(["yes", "bus", "train", "tram", "metro"])][["geometry"]],
                   lots[["geometry"]].rename_axis(None), predicate="intersects")
    is_pr = set(pr.index_right)
    rows = {}
    for i, row in lots.iterrows():
        geom = row.geometry
        typ = "Parkeerterrein"
        if i in is_pr:
            typ = "P+R-terrein"
        else:
            for kind, reach, fmt in order:
                p = places[places.kind == kind]
                d = p.distance(geom)
                if len(d) and d.min() <= reach:
                    nm = p.loc[d.idxmin(), "name"]
                    if "{}" in fmt and not nm:
                        continue
                    phrase = fmt.format(nm.replace("Station ", "")) if "{}" in fmt else fmt
                    typ = f"Parkeerterrein {phrase}"
                    break
        near = vbo.iloc[vbo.sindex.nearest(geom.representative_point(), return_all=False)[1]]
        street = near.openbare_ruimte_naam.iloc[0] if len(near) else ""
        rows[i] = {"naam": typ, "straat": street}
    return pd.DataFrame.from_dict(rows, orient="index")


def main():
    ensure_dirs()
    buurten = gpd.read_parquet(WORK / "buurt_land.parquet")
    cand, osm_kept, rijbaan = candidates()
    log("candidates", cand.bron.value_counts().to_dict())
    cache = WORK / "parking_merged.parquet"
    if cache.exists() and cache.stat().st_mtime > max((WORK / f).stat().st_mtime
                                                      for f in ("bgt_wegdeel.parquet", "osm_parking.parquet")):
        pieces = gpd.read_parquet(cache)
    else:
        pieces = merge_pieces(cand)
        pieces.to_parquet(cache)
    log("merged pieces", len(pieces))
    pieces = classify(pieces, rijbaan)
    log("classes", pieces.klasse.value_counts().to_dict(),
        {k: round(v / 1e4, 1) for k, v in pieces.groupby("klasse").opp_m2.sum().items()}, "ha")
    pieces, ov = value(pieces, buurten)
    pieces.to_parquet(WORK / "parking_pieces.parquet")

    lots = pieces[pieces.klasse == "terrein"].copy()
    lots = lots.join(name_lots(lots, osm_kept))
    lots["label"] = lots.naam + ", " + lots.straat.fillna("") + " (" + lots.buurtnaam.fillna("") + ")"

    # Per buurt totals.
    per_b = ov.copy()
    per_b["klasse"] = per_b.klasse.where(per_b.klasse != "gebouwd", "gebouwd")
    agg = {}
    for k in ("terrein", "straat"):
        sub = per_b[per_b.klasse == k]
        agg[f"{k}_m2"] = sub.groupby("buurtcode").m2.sum()
        for v in VARIANTS:
            agg[f"{k}_waarde_{v}"] = sub[sub.bron_grondprijs == "buurt"].groupby("buurtcode")[f"waarde_{v}"].sum()
    bt = pd.DataFrame(agg).fillna(0.0)
    bt = buurten[["buurtcode", "buurtnaam", "stadsdeel", "bron_grondprijs"]].merge(bt, left_on="buurtcode",
                                                                                   right_index=True, how="left")
    bt = bt.fillna({c: 0.0 for c in agg})
    bt.round(0).to_csv(OUT / "buurt_parkeren.csv", index=False)

    top = lots[lots.bron_grondprijs == "buurt"].sort_values("waarde_central", ascending=False).head(20).copy()
    dup = top.groupby("label").cumcount()
    top["label"] = np.where(dup > 0, top.label + " – terrein " + (dup + 1).astype(str), top.label)
    top_out = top[["label", "naam", "straat", "buurtcode", "buurtnaam", "stadsdeel", "opp_m2", "opp_onbebouwd_m2", "bron",
                   *[f"waarde_{v}" for v in VARIANTS]]].copy()
    top_out["rang"] = range(1, len(top_out) + 1)
    top_out.round(0).to_csv(OUT / "top20_parkeerterreinen.csv", index=False)

    lots_out = lots[["label", "buurtcode", "buurtnaam", "stadsdeel", "bron_grondprijs", "opp_m2", "opp_onbebouwd_m2",
                     "bebouwd_aandeel", "bron", *[f"waarde_{v}" for v in VARIANTS], "geometry"]].copy()
    lots_out["geometry"] = lots_out.geometry.simplify(0.5)
    lots_out.round({"opp_m2": 0, "opp_onbebouwd_m2": 0, "bebouwd_aandeel": 2, **{f"waarde_{v}": -3 for v in VARIANTS}}) \
        .to_crs("EPSG:4326").to_file(OUT / "parkeerterreinen.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)

    gem_m2 = float(buurten[buurten.water == "NEE"].geometry.area.sum())
    s = {
        "kandidaten": cand.bron.value_counts().to_dict(),
        "stukken": pieces.klasse.value_counts().to_dict(),
        "gemeente_land_m2": gem_m2,
    }
    for k in ("terrein", "straat", "gebouwd"):
        sub = pieces[pieces.klasse == k]
        s[k] = {"aantal": int(len(sub)), "m2": float(sub.opp_m2.sum()),
                "m2_onbebouwd": float(sub.opp_onbebouwd_m2.sum()),
                "m2_gewaardeerd": float(sub.m2_gewaardeerd.sum()),
                **{f"waarde_{v}": float(sub[f"waarde_{v}"].sum()) for v in VARIANTS},
                **{f"waarde_indicatief_{v}": float(sub[f"waarde_indicatief_{v}"].sum()) for v in VARIANTS}}
    s["terrein"]["aantal_gewaardeerd"] = int((lots.m2_gewaardeerd > 0).sum())
    s["terrein"]["m2_geen_eigen_tarief"] = float(lots.opp_onbebouwd_m2.sum() - lots.m2_gewaardeerd.sum())
    s["top20"] = [{"rang": int(r.rang), "label": r.label, "naam": r.naam, "straat": r.straat, "buurt": r.buurtnaam,
                   "stadsdeel": r.stadsdeel, "m2": round(float(r.opp_onbebouwd_m2)),
                   **{f"waarde_{v}": float(getattr(r, f"waarde_{v}")) for v in VARIANTS}}
                  for r in top_out.itertuples()]
    s["top20_aandeel_central"] = float(top.waarde_central.sum() / lots.waarde_central.sum())
    s["per_stadsdeel"] = {sd: {"terrein_m2": float(g_.opp_onbebouwd_m2.sum()), "terrein_waarde_central":
                               float(g_.waarde_central.sum()), "aantal": int(len(g_))}
                          for sd, g_ in lots.groupby("stadsdeel")}
    write_json(WORK / "summary_parking.json", s, indent=1)
    write_json(OUT / "samenvatting_parkeren.json", s, indent=1)
    log("summary", {k: v for k, v in s.items() if k not in ("top20", "per_stadsdeel")})
    for r in s["top20"]:
        log(r)


if __name__ == "__main__":
    main()
