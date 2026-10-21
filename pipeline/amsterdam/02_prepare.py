# /// script
# requires-python = ">=3.11"
# dependencies = ["geopandas>=1.0", "pyogrio>=0.9", "pyarrow>=15", "shapely>=2.0", "pandas>=2.2", "numpy>=1.26"]
# ///
"""Parse the raw downloads into clean GeoParquet files clipped to Amsterdam.

    uv run 02_prepare.py

Reads  cache/raw/...  (see 01_fetch.py)
Writes cache/work/{buurten,vbo,panden,percelen,bgt_wegdeel,osm_parking,osm_places,grid}.parquet
"""

from __future__ import annotations

import glob
import re
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import make_valid
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, shape
from shapely.ops import polygonize, unary_union

from common import RAW, RD, WGS84, WORK, ensure_dirs, log, params, read_json

P = params()
KAART = P["area"]["cbs_buurtkaart"]


def num(v):
    return np.nan if v is None or (isinstance(v, (int, float)) and v <= -99990) else v


# ---------------------------------------------------------------- buurten
def prepare_buurten():
    b = read_json(RAW / "cbs" / f"buurten_{KAART}.geojson")["features"]
    w = read_json(RAW / "cbs" / f"wijken_{KAART}.geojson")["features"]
    g = read_json(RAW / "cbs" / f"gemeenten_{KAART}.geojson")["features"]
    wijknaam = {f["properties"]["wijkcode"]: f["properties"]["wijknaam"] for f in w}
    rows = []
    for f in b:
        p = f["properties"]
        rows.append({"buurtcode": p["buurtcode"], "buurtnaam": p["buurtnaam"].strip(),
                     "wijkcode": p["wijkcode"], "wijknaam": wijknaam.get(p["wijkcode"], "").strip(),
                     "water": p.get("water"), "geometry": make_valid(shape(f["geometry"]))})
    buurten = gpd.GeoDataFrame(rows, crs=RD)
    gem = gpd.GeoDataFrame([{"water": f["properties"]["water"], "geometry": make_valid(shape(f["geometry"]))}
                            for f in g], crs=RD)
    buurten.to_parquet(WORK / "buurten.parquet")
    gem.to_parquet(WORK / "gemeente.parquet")
    log("buurten", len(buurten), "gemeente parts", len(gem))
    return buurten, unary_union(gem.geometry.values)


# ---------------------------------------------------------------- BAG
def prepare_bag(buurten, gem):
    path = RAW / "bag" / "bag-light.gpkg"
    bbox = tuple(gem.bounds)
    la = P["land_area"]
    vbo = pyogrio.read_dataframe(path, layer="verblijfsobject", bbox=bbox,
                                 columns=["identificatie", "oppervlakte", "status", "gebruiksdoel",
                                          "openbare_ruimte_naam", "bouwjaar", "pand_identificatie", "pandstatus"])
    log("vbo in bbox", len(vbo))
    vbo = vbo[vbo.status.isin(la["vbo_status"])].copy()
    vbo = gpd.sjoin(vbo, buurten[["buurtcode", "geometry"]], how="inner", predicate="within").drop(columns="index_right")
    vbo["woon"] = vbo.gebruiksdoel.fillna("").str.contains("woonfunctie")
    vbo.to_parquet(WORK / "vbo.parquet")
    log("vbo in gemeente, in gebruik", len(vbo), "woon", int(vbo.woon.sum()))

    panden = pyogrio.read_dataframe(path, layer="pand", bbox=bbox,
                                    columns=["identificatie", "bouwjaar", "status", "gebruiksdoel",
                                             "aantal_verblijfsobjecten"])
    panden = panden[panden.status.isin(la["pand_status"])].copy()
    panden = panden[panden.intersects(gem)].copy()
    panden["geometry"] = panden.geometry.make_valid()
    panden.to_parquet(WORK / "panden.parquet")
    log("panden in gemeente", len(panden))


# ---------------------------------------------------------------- DKK
def prepare_percelen(gem):
    if not (RAW / "dkk" / "COMPLETE").exists():
        raise SystemExit("DKK download incomplete; run 01_fetch.py dkk")
    seen, rows = set(), []
    for fn in sorted(glob.glob(str(RAW / "dkk" / "tiles" / "*.json"))):
        for f in read_json(fn)["features"]:
            p = f["properties"]
            pid = p["identificatie_lokaal_id"]
            if pid in seen:
                continue
            seen.add(pid)
            rows.append({"perceel_id": pid, "kadastrale_grootte": p.get("kadastrale_grootte_waarde"),
                         "geometry": shape(f["geometry"])})
    perc = gpd.GeoDataFrame(rows, crs=RD)
    perc["geometry"] = perc.geometry.make_valid()
    perc = perc[perc.intersects(gem)].copy()
    perc.to_parquet(WORK / "percelen.parquet")
    log("percelen", len(perc))


# ---------------------------------------------------------------- BGT
NS = {"imgeo": "http://www.geostandaarden.nl/imgeo/2.1/simple/gml31", "gml": "http://www.opengis.net/gml"}
KEEP = re.compile(r"^(parkeervlak|rijbaan.*|woonerf|busbaan|baan voor vliegverkeer)$")


def _coords(ring_el):
    pts = []
    for el in ring_el.iter():
        tag = el.tag.split("}")[-1]
        if tag == "posList" and el.text:
            v = np.array(el.text.split(), dtype=float)
            dim = int(el.get("srsDimension", "2"))
            pts.extend(v.reshape(-1, dim)[:, :2].tolist())
        elif tag == "pos" and el.text:
            pts.append([float(x) for x in el.text.split()[:2]])
    return pts


def _polygon(poly_el):
    ext = poly_el.find("gml:exterior", NS)
    if ext is None:
        return None
    shell = _coords(ext)
    holes = [_coords(i) for i in poly_el.findall("gml:interior", NS)]
    if len(shell) < 4:
        return None
    return Polygon(shell, [h for h in holes if len(h) >= 4])


def prepare_bgt(gem):
    z = zipfile.ZipFile(RAW / "bgt" / "bgt_wegdeel.zip")
    name = next(n for n in z.namelist() if n.endswith(".gml"))
    rows = []
    n_all = 0
    with z.open(name) as fh:
        ctx = ET.iterparse(fh, events=("end",))
        for _, el in ctx:
            if not el.tag.endswith("}Wegdeel"):
                continue
            n_all += 1
            g = lambda t: (el.findtext(f"imgeo:{t}", default=None, namespaces=NS) or "").strip()
            functie = g("bgt-functie")
            if not g("eindRegistratie") and g("bgt-status") == "bestaand" and KEEP.match(functie):
                geom_el = el.find("imgeo:geometrie2d", NS)
                polys = [_polygon(p) for p in geom_el.iter(f"{{{NS['gml']}}}Polygon")] if geom_el is not None else []
                polys = [p for p in polys if p is not None]
                if polys:
                    geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
                    rows.append({"lokaal_id": g("identificatie.lokaalID"), "functie": functie,
                                 "fysiek": g("bgt-fysiekVoorkomen"), "plus_functie": g("plus-functieWegdeel") or g("plus-functie"),
                                 "hoogte": int(g("relatieveHoogteligging") or 0), "bronhouder": g("bronhouder"),
                                 "geometry": geom})
            el.clear()
    wd = gpd.GeoDataFrame(rows, crs=RD)
    wd["geometry"] = wd.geometry.make_valid()
    wd = wd[wd.intersects(gem)].copy()
    wd.to_parquet(WORK / "bgt_wegdeel.parquet")
    log("bgt wegdeel features read", n_all, "kept", len(wd), wd.functie.value_counts().to_dict())


# ---------------------------------------------------------------- OSM
def _osm_geom(e):
    if e["type"] == "way" and "geometry" in e:
        pts = [(p["lon"], p["lat"]) for p in e["geometry"]]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return None
    if e["type"] == "relation":
        lines = []
        for m in e.get("members", []):
            if m.get("type") == "way" and m.get("geometry") and m.get("role") in ("outer", ""):
                lines.append(LineString([(p["lon"], p["lat"]) for p in m["geometry"]]))
        polys = list(polygonize(unary_union(lines))) if lines else []
        inners = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                  for m in e.get("members", []) if m.get("role") == "inner" and m.get("geometry")]
        if not polys:
            return None
        geom = unary_union(polys)
        for h in polygonize(unary_union(inners)) if inners else []:
            geom = geom.difference(h)
        return geom
    return None


def prepare_osm(gem):
    rows, seen = [], set()
    for fn in sorted(glob.glob(str(RAW / "osm" / "parking_*.json"))):
        for e in read_json(fn).get("elements", []):
            key = (e["type"], e["id"])
            if key in seen:
                continue
            seen.add(key)
            geom = _osm_geom(e)
            if geom is None or geom.is_empty:
                continue
            t = e.get("tags", {})
            rows.append({"osm_id": f"{e['type']}/{e['id']}", "parking": t.get("parking", ""),
                         "access": t.get("access", ""), "park_ride": t.get("park_ride", ""),
                         "name": t.get("name", ""), "building": t.get("building", ""),
                         "layer": t.get("layer", ""), "location": t.get("location", ""),
                         "geometry": geom})
    osm = gpd.GeoDataFrame(rows, crs=WGS84).to_crs(RD)
    osm["geometry"] = osm.geometry.make_valid()
    osm = osm[osm.intersects(gem)].copy()
    osm.to_parquet(WORK / "osm_parking.parquet")
    log("osm parking", len(osm), osm.parking.value_counts().head(8).to_dict())

    rows = []
    for e in read_json(RAW / "osm" / "places.json").get("elements", []):
        t = e.get("tags", {})
        c = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
        if not c:
            continue
        kind = ("winkelcentrum" if t.get("shop") == "mall" else
                "supermarkt" if t.get("shop") == "supermarket" else
                "station" if t.get("railway") == "station" else
                "ziekenhuis" if t.get("amenity") == "hospital" else
                "onderwijsinstelling" if t.get("amenity") in ("university", "college") else
                "stadion" if t.get("leisure") == "stadium" else
                "woonwinkel" if t.get("shop") in ("furniture", "doityourself", "garden_centre") else
                "winkelgebied" if t.get("landuse") == "retail" else "")
        if not kind:
            continue
        # Only place names (stations, winkelcentra, stadions, hospitals) are kept;
        # shop brand names are dropped so lots are not named after a company.
        nm = t.get("name", "") if kind in ("winkelcentrum", "station", "ziekenhuis", "stadion",
                                           "onderwijsinstelling", "winkelgebied") else ""
        rows.append({"kind": kind, "name": nm, "geometry": Point(c["lon"], c["lat"])})
    places = gpd.GeoDataFrame(rows, crs=WGS84).to_crs(RD)
    places = places[places.within(gem.buffer(500))].copy()
    places.to_parquet(WORK / "osm_places.parquet")
    log("osm places", len(places), places.kind.value_counts().to_dict())


# ---------------------------------------------------------------- CBS grid
def prepare_grid(gem):
    if not (RAW / "grid" / "COMPLETE").exists():
        log("grid download incomplete; skipping")
        return
    seen, rows = set(), []
    for fn in sorted(glob.glob(str(RAW / "grid" / "tiles" / "*.json"))):
        for f in read_json(fn)["features"]:
            p = f["properties"]
            cid = p["crs28992res100m"]
            if cid in seen:
                continue
            seen.add(cid)
            rows.append({"cell": cid, "woz": num(p.get("gemiddelde_woz_waarde_woning")),
                         "woningen": num(p.get("aantal_woningen")),
                         "koop_pct": num(p.get("percentage_koopwoningen")),
                         "geometry": shape(f["geometry"])})
    grid = gpd.GeoDataFrame(rows, crs=RD)
    grid = grid[grid.intersects(gem)].copy()
    grid.to_parquet(WORK / "grid.parquet")
    log("grid cells", len(grid), "with woz", int(grid.woz.notna().sum()))


if __name__ == "__main__":
    import sys

    ensure_dirs()
    want = sys.argv[1:] or ["buurten", "bag", "percelen", "bgt", "osm", "grid"]
    buurten, gem_all = prepare_buurten()
    if "bag" in want:
        prepare_bag(buurten, gem_all)
    if "percelen" in want:
        prepare_percelen(gem_all)
    if "bgt" in want:
        prepare_bgt(gem_all)
    if "osm" in want:
        prepare_osm(gem_all)
    if "grid" in want:
        prepare_grid(gem_all)
