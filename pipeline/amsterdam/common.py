"""Shared helpers for the Amsterdam pipeline: paths, parameters, HTTP, logging.

Imported by the numbered scripts in this folder. Downloaded files are treated
as untrusted data: they are only parsed (JSON, XML, GeoPackage, GML), never
executed.
"""

from __future__ import annotations

import json
import os
import sys
import time
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CACHE = Path(os.environ.get("AMS_CACHE", HERE / "cache")).resolve()
RAW = CACHE / "raw"          # downloads, untouched
WORK = CACHE / "work"        # intermediate parquet files
OUT = HERE / "output"        # CSV/GeoJSON deliverables (committed, small)
SITE_DATA = REPO / "data" / "amsterdam"        # JSON read by Hugo templates
SITE_STATIC = REPO / "static" / "amsterdam"    # map data and images served as-is

USER_AGENT = "wonenisteduur-amsterdam-pipeline/1.0 (+https://wonenisteduur.nl)"

RD = "EPSG:28992"
WGS84 = "EPSG:4326"


def params() -> dict:
    with open(HERE / "params.toml", "rb") as f:
        return tomllib.load(f)


def log(*args) -> None:
    print(time.strftime("%H:%M:%S"), *args, file=sys.stderr, flush=True)


def ensure_dirs() -> None:
    for d in (RAW, WORK, OUT, SITE_DATA, SITE_STATIC):
        d.mkdir(parents=True, exist_ok=True)


def session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    retry = Retry(total=6, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "POST"))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
    return s


def _np_default(o):
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o)}")


def write_json(path: Path, obj, indent: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"),
                  default=_np_default)
        f.write("\n")
    tmp.replace(path)


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def variants() -> tuple[str, str, str]:
    return ("low", "central", "high")


# Dutch number formatting for the site texts (06_publish.py, 07_grondstaffel.py).
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
