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
