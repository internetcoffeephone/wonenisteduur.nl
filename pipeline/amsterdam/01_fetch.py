# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31", "shapely>=2.0"]
# ///
"""Download every open dataset the Amsterdam pipeline needs into the cache.

    uv run 01_fetch.py            # all sources, skipping files already present
    uv run 01_fetch.py dkk osm    # only some sources

Sources (all open, see README for licences):
  cbs     CBS OData: 86165NED (buurten), 83642NED (OZB), 83673NED (bouwkosten),
          84550NED (grond onder woningen) and the PDOK Wijk- en buurtkaart 2025
  cvdr    Amsterdam Verordening Onroerendezaakbelastingen (CVDR XML)
  grid    CBS 100 m vierkantstatistieken 2023 (PDOK OGC API)
  dkk     Kadastrale kaart percelen (PDOK OGC API, 1 km tiles)
  bgt     BGT wegdeel (PDOK BGT download API, custom extract)
  osm     OpenStreetMap amenity=parking and a few named places (Overpass API)
  bag     BAG light GeoPackage (PDOK bulk download, ~7.8 GB)

Nothing in this script calls the WOZ-waardeloket, kadaster.nl or BRK owner data.
"""

from __future__ import annotations

import concurrent.futures as cf
import sys
import time
import zipfile

from common import RAW, RD, ensure_dirs, log, params, read_json, session, write_json

P = params()
GM = P["area"]["gemeentecode"]
X0, Y0, X1, Y1 = P["area"]["bbox_rd"]
RD_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"
CBS_ODATA = "https://opendata.cbs.nl/ODataApi/odata"
PDOK = "https://api.pdok.nl"


def get_json(s, url, **params_):
    r = s.get(url, params=params_ or None, timeout=180)
    r.raise_for_status()
    return r.json()


def ogc_items(s, url, **query):
    """Follow OGC API Features `next` links and return all features."""
    feats = []
    nxt = url
    q = dict(query)
    while nxt:
        d = get_json(s, nxt, **q) if q else get_json(s, nxt)
        feats.extend(d.get("features", []))
        nxt = next((ln["href"] for ln in d.get("links", []) if ln.get("rel") == "next"), None)
        q = {}
    return feats


# ---------------------------------------------------------------- CBS
def fetch_cbs(s):
    out = RAW / "cbs"
    out.mkdir(parents=True, exist_ok=True)
    tab = P["area"]["cbs_kerncijfers"]
    code = GM[2:]
    f = out / f"{tab}_ams.json"
    if not f.exists():
        rows = []
        for prefix in (f"BU{code}", f"WK{code}", f"GM{code}"):
            d = get_json(s, f"{CBS_ODATA}/{tab}/TypedDataSet",
                         **{"$filter": f"substringof('{prefix}',WijkenEnBuurten)", "$format": "json"})
            rows.extend(d["value"])
        nl = get_json(s, f"{CBS_ODATA}/{tab}/TypedDataSet",
                      **{"$filter": "substringof('NL00',WijkenEnBuurten)", "$format": "json"})
        rows.extend(nl["value"])
        props = get_json(s, f"{CBS_ODATA}/{tab}/DataProperties", **{"$format": "json"})["value"]
        write_json(f, {"table": tab, "rows": rows, "properties": props})
        log("cbs", tab, len(rows), "rows")

    f = out / "83642NED_ams.json"
    if not f.exists():
        d = get_json(s, f"{CBS_ODATA}/83642NED/TypedDataSet",
                     **{"$filter": f"startswith(RegioS,'{GM}')", "$format": "json"})
        write_json(f, {"table": "83642NED", "rows": d["value"]})
        log("cbs 83642NED", len(d["value"]), "rows")

    f = out / "83673NED.json"
    if not f.exists():
        d = get_json(s, f"{CBS_ODATA}/83673NED/TypedDataSet",
                     **{"$filter": "substringof('VJ12',Perioden)", "$format": "json"})
        write_json(f, {"table": "83673NED", "rows": d["value"]})
        log("cbs 83673NED", len(d["value"]), "rows")

    f = out / "84550NED.json"
    if not f.exists():
        d = get_json(s, f"{CBS_ODATA}/84550NED/TypedDataSet",
                     **{"$filter": "Sectoren eq 'A044923' and (TypeNietFinancieleActiva eq 'A047162' "
                                   "or TypeNietFinancieleActiva eq 'A047182')", "$format": "json"})
        write_json(f, {"table": "84550NED", "rows": d["value"]})
        log("cbs 84550NED", len(d["value"]), "rows")

    kaart = P["area"]["cbs_buurtkaart"]
    for coll in ("buurten", "wijken", "gemeenten"):
        f = out / f"{coll}_{kaart}.geojson"
        if f.exists():
            continue
        feats = ogc_items(s, f"{PDOK}/cbs/{kaart}/ogc/v1/collections/{coll}/items",
                          f="json", gemeentecode=GM, limit=1000, crs=RD_URI)
        write_json(f, {"type": "FeatureCollection", "crs_note": RD, "features": feats})
        log("cbs kaart", coll, len(feats))


# ---------------------------------------------------------------- CVDR
def fetch_cvdr(s):
    out = RAW / "cvdr"
    out.mkdir(parents=True, exist_ok=True)
    cid = P["ozb"]["cvdr_id"]
    f = out / f"{cid}.xml"
    if f.exists():
        return
    base, ver = cid.split("_")
    url = f"https://repository.officiele-overheidspublicaties.nl/CVDR/{base}/{ver}/xml/{cid}.xml"
    r = s.get(url, timeout=60)
    r.raise_for_status()
    f.write_bytes(r.content)
    log("cvdr", cid, len(r.content), "bytes")


# ---------------------------------------------------------------- tiles
def gemeente_shape():
    from shapely.geometry import shape
    from shapely.ops import unary_union

    gj = read_json(RAW / "cbs" / f"gemeenten_{P['area']['cbs_buurtkaart']}.geojson")
    return unary_union([shape(f["geometry"]) for f in gj["features"]])


def rd_tiles(size: int, buffer: float = 50):
    from shapely.geometry import box

    gem = gemeente_shape().buffer(buffer)
    tiles = []
    for x in range(int(X0 // size * size), int(X1), size):
        for y in range(int(Y0 // size * size), int(Y1), size):
            if box(x, y, x + size, y + size).intersects(gem):
                tiles.append((x, y, x + size, y + size))
    return tiles


def fetch_tiled(s, name, url, size, extra):
    out = RAW / name / "tiles"
    out.mkdir(parents=True, exist_ok=True)
    tiles = rd_tiles(size)
    todo = [t for t in tiles if not (out / f"{t[0]}_{t[1]}.json").exists()]
    log(name, len(tiles), "tiles,", len(todo), "to fetch")

    def one(t):
        feats = ogc_items(s, url, f="json", limit=1000, bbox=",".join(map(str, t)),
                          **{"bbox-crs": RD_URI, "crs": RD_URI}, **extra)
        write_json(out / f"{t[0]}_{t[1]}.json", {"bbox": t, "features": feats})
        return len(feats)

    n = 0
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i, k in enumerate(ex.map(one, todo)):
            n += k
            if i % 25 == 0:
                log(name, f"{i + 1}/{len(todo)} tiles, {n} features")
    (RAW / name / "COMPLETE").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))


def fetch_dkk(s):
    fetch_tiled(s, "dkk", f"{PDOK}/kadaster/brk-kadastrale-kaart/ogc/v1/collections/perceel/items", 1000, {})


def fetch_grid(s):
    fetch_tiled(s, "grid", f"{PDOK}/cbs/vierkantstatistieken100m/ogc/v1/collections/vierkant100/items",
                2000, {"jaarcode": 2023})


# ---------------------------------------------------------------- BGT
def fetch_bgt(s):
    out = RAW / "bgt"
    out.mkdir(parents=True, exist_ok=True)
    f = out / "bgt_wegdeel.zip"
    if f.exists():
        return
    base = f"{PDOK}/lv/bgt/download/v1_0"
    poly = f"POLYGON(({X0} {Y0},{X1} {Y0},{X1} {Y1},{X0} {Y1},{X0} {Y0}))"
    r = s.post(f"{base}/full/custom", json={"featuretypes": ["wegdeel"], "format": "gmllight", "geofilter": poly},
               timeout=60)
    r.raise_for_status()
    rid = r.json()["downloadRequestId"]
    while True:
        st = get_json(s, f"{base}/full/custom/{rid}/status")
        log("bgt", st.get("status"), st.get("progress"))
        if st.get("status") == "COMPLETED":
            href = st["_links"]["download"]["href"]
            break
        if st.get("status") not in ("PENDING", "RUNNING"):
            raise RuntimeError(f"BGT download failed: {st}")
        time.sleep(10)
    url = "https://api.pdok.nl" + href.replace("/kadaster/bgt/download/v1_0", "/lv/bgt/download/v1_0") \
        if href.startswith("/") else href
    with s.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        tmp = f.with_suffix(".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    zipfile.ZipFile(tmp).testzip()
    tmp.replace(f)
    log("bgt", f.stat().st_size, "bytes")


# ---------------------------------------------------------------- OSM
OVERPASS = "https://overpass-api.de/api/interpreter"


def fetch_osm(s):
    out = RAW / "osm"
    out.mkdir(parents=True, exist_ok=True)
    # WGS84 box around the gemeente, split in 6 tiles to keep queries small.
    s_, w, n, e = 52.27, 4.72, 52.44, 5.11
    lats = [s_ + i * (n - s_) / 2 for i in range(3)]
    lons = [w + i * (e - w) / 3 for i in range(4)]
    for i in range(2):
        for j in range(3):
            f = out / f"parking_{i}_{j}.json"
            if f.exists():
                continue
            bb = f"{lats[i]:.5f},{lons[j]:.5f},{lats[i + 1]:.5f},{lons[j + 1]:.5f}"
            q = (f"[out:json][timeout:180];(way[amenity=parking]({bb});relation[amenity=parking]({bb}););"
                 f"out tags geom;")
            r = s.post(OVERPASS, data={"data": q}, timeout=300)
            r.raise_for_status()
            write_json(f, r.json())
            log("osm parking tile", i, j, len(r.json().get("elements", [])))
            time.sleep(5)
    f = out / "places.json"
    if not f.exists():
        bb = f"{s_},{w},{n},{e}"
        q = (f"[out:json][timeout:180];(nwr[shop=mall][name]({bb});nwr[shop=supermarket]({bb});"
             f"nwr[railway=station][name]({bb});nwr[amenity~\"^(hospital|university|college)$\"][name]({bb});"
             f"nwr[leisure=stadium][name]({bb});nwr[shop~\"^(furniture|doityourself|garden_centre)$\"]({bb});"
             f"nwr[landuse=retail]({bb}););out tags center;")
        r = s.post(OVERPASS, data={"data": q}, timeout=300)
        r.raise_for_status()
        write_json(f, r.json())
        log("osm places", len(r.json().get("elements", [])))


# ---------------------------------------------------------------- BAG
def fetch_bag(s):
    out = RAW / "bag"
    out.mkdir(parents=True, exist_ok=True)
    f = out / "bag-light.gpkg"
    if f.exists() and not (out / "bag-light.gpkg.part").exists():
        return
    url = "https://service.pdok.nl/kadaster/bag/atom/downloads/bag-light.gpkg"
    log("bag: downloading ~7.8 GB, this takes a while")
    with s.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(f, "wb") as fh:
            for chunk in r.iter_content(8 << 20):
                fh.write(chunk)
    log("bag", f.stat().st_size, "bytes")


STEPS = {"cbs": fetch_cbs, "cvdr": fetch_cvdr, "grid": fetch_grid, "dkk": fetch_dkk,
         "bgt": fetch_bgt, "osm": fetch_osm, "bag": fetch_bag}

if __name__ == "__main__":
    ensure_dirs()
    want = sys.argv[1:] or list(STEPS)
    sess = session()
    if any(w in ("dkk", "grid") for w in want):
        fetch_cbs(sess)  # tiles need the gemeente outline
    for name in want:
        log("==", name)
        STEPS[name](sess)
