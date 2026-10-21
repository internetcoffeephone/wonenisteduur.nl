#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Grond in cijfers: fetch CBS tables, compute the figures, write Hugo data and SVG charts.

Run from the repository root:

    uv run pipeline/cijfers/build.py            # download fresh data, then build
    uv run pipeline/cijfers/build.py --offline  # rebuild from the cache only

Outputs:
    data/cijfers.json        numbers and formatted Dutch strings for the page
    static/cijfers/*.svg     the charts, in a wide and a narrow (phone) variant

Downloaded data is only ever parsed as JSON; nothing from it is executed, and
no downloaded text is copied into the charts (only numbers). See README.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "cache"
OUT_JSON = ROOT / "data" / "cijfers.json"
OUT_SVG = ROOT / "static" / "cijfers"
SVG_URL = "cijfers/"  # relative to the site root; templates pass it through relURL

CBS_API = "https://opendata.cbs.nl/ODataApi/odata/"
STATLINE = "https://opendata.cbs.nl/statline/#/CBS/nl/dataset/{}/table"
USER_AGENT = "wonenisteduur-cijfers/1.0 (+https://wonenisteduur.nl/grond-in-cijfers/)"

# CBS codes used (see README.md for definitions).
SECTOR_TOTAL = "A044923"  # Totaal alle sectoren
LAND = "A047181"  # AN211 Grond
AGRI_LAND = "A047184"  # AN2112 Landbouwgrond
DWELLINGS = "A047162"  # AN111 Woningen (the buildings, "stenen")
LAND_DWELLINGS = "A047182"  # AN2111A Grond onder woningen
GDP_CURRENT = "A045297"  # Werkelijke prijzen
OZB_TOTAL, OZB_HOMES, OZB_OTHER = "A046999", "A047000", "A047001"
NL = "NL01"
CPI_ALL = "T001112"  # Alle bestedingen

# Base year for the "stenen vs grond" decomposition; it matches the homepage claim.
BASE_YEAR = 2013

# --------------------------------------------------------------------------- fetching


def _get(url: str) -> dict:
    if not url.startswith(CBS_API):
        raise ValueError(f"refusing to fetch outside the CBS API: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                if resp.status != 200:
                    raise OSError(f"HTTP {resp.status}")
                body = resp.read()
            data = json.loads(body)
            if not isinstance(data, dict) or not isinstance(data.get("value"), list):
                raise ValueError(f"unexpected response shape from {url}")
            return data
        except (OSError, ValueError) as exc:  # urllib errors are OSErrors
            if attempt == 3:
                raise SystemExit(f"download failed: {url}\n  {exc}") from exc
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def cbs(table: str, endpoint: str, name: str, offline: bool, filt: str | None = None,
        select: str | None = None) -> list[dict]:
    """Fetch one CBS OData endpoint (following nextLink pages) via the cache."""
    cache_file = CACHE / f"{table}_{name}.json"
    if offline:
        if not cache_file.exists():
            raise SystemExit(f"--offline: {cache_file.relative_to(ROOT)} is missing; run once without --offline")
        return json.loads(cache_file.read_text("utf-8"))["value"]
    params = {}
    if filt:
        params["$filter"] = filt
    if select:
        params["$select"] = select
    url = f"{CBS_API}{table}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    rows: list[dict] = []
    next_url: str | None = url
    while next_url:
        data = _get(next_url)
        rows.extend(data["value"])
        next_url = data.get("odata.nextLink")
    CACHE.mkdir(exist_ok=True)
    payload = {"url": url, "opgehaald": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "value": rows}
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    return rows


def num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"expected a number, got {v!r}")
    return float(v)


def year_of(period: str) -> int:
    if not (isinstance(period, str) and len(period) == 8 and period[4:] == "JJ00" and period[:4].isdigit()):
        raise ValueError(f"unexpected period code {period!r}")
    return int(period[:4])


def series(rows: list[dict], key_field: str, key: str, value_field: str) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rows:
        if str(r.get(key_field, "")).strip() != key or not str(r.get("Perioden", "")).endswith("JJ00"):
            continue
        v = num(r.get(value_field))
        if v is not None:
            out[year_of(r["Perioden"])] = v
    if not out:
        raise SystemExit(f"no data for {key} / {value_field}")
    return out


def table_meta(table: str, offline: bool) -> tuple[dict, list[int]]:
    """Table title, modification date and provisional years, plus all annual periods on offer."""
    info = cbs(table, "TableInfos", "TableInfos", offline)[0]
    annual = [p for p in cbs(table, "Perioden", "Perioden", offline) if str(p.get("Key", "")).endswith("JJ00")]
    provisional = sorted(year_of(p["Key"]) for p in annual if p.get("Status") not in (None, "Definitief"))
    meta = {
        "tabel": table,
        "titel": str(info.get("Title", "")).strip(),
        "gewijzigd": str(info.get("Modified", ""))[:10],
        "gewijzigd_tekst": nl_date(dt.date.fromisoformat(str(info.get("Modified", ""))[:10])),
        "url": STATLINE.format(table),
        "voorlopig": provisional,
    }
    return meta, sorted(year_of(p["Key"]) for p in annual)


# --------------------------------------------------------------------------- Dutch formatting

MONTHS = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
          "september", "oktober", "november", "december"]


def nl(x: float, dec: int = 0) -> str:
    s = f"{x:,.{dec}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def pct(x: float, dec: int = 0) -> str:
    return f"{nl(x, dec)}%"


def signed_pct(x: float) -> str:
    r = round(x)
    return ("+" if r > 0 else "−" if r < 0 else "") + f"{nl(abs(r))}%"


def signed_pct_1(x: float) -> str:
    r = round(x, 1)
    return ("+" if r > 0 else "−" if r < 0 else "") + f"{nl(abs(r), 1)}%"


def mld(x_mln: float, dec: int = 0) -> str:
    return f"€{nl(x_mln / 1000, dec)} miljard"


def nl_date(d: dt.date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def star(year: int, provisional: list[int]) -> str:
    return f"{year}*" if year in provisional else str(year)


# --------------------------------------------------------------------------- SVG primitives

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif"
COL = {
    "surface": "#fafaf8",  # site background
    "title": "#2c3e50",  # site heading navy
    "ink": "#2c2c2c",  # site text
    "ink2": "#5c5a54",  # secondary text, 6.6:1 on surface
    "muted": "#6b685f",  # axis labels, 5.3:1 on surface
    "grid": "#e0ddd6",  # site border colour, hairline grid
    "axis": "#b9b4a9",  # baseline
    "grond": "#5f8a3f",  # sage, stepped darker so it clears 3:1 (validated)
    "stenen": "#226198",  # navy hue stepped into the lightness band (validated)
}
CHAR_W = 0.6  # generous average glyph width (fits wide fallback fonts such as DejaVu Sans)


def text_w(s: str, size: float, bold: bool = False) -> float:
    return len(s) * size * (CHAR_W + (0.04 if bold else 0))


def wrap(s: str, size: float, max_w: float, bold: bool = False) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and text_w(trial, size, bold) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


class Svg:
    def __init__(self, width: int):
        self.w = width
        self.items: list[str] = []

    def text(self, x, y, s, size=13, fill=COL["ink"], bold=False, anchor="start", tabular=False):
        attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}"'
        if bold:
            attrs += ' font-weight="600"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if tabular:
            attrs += ' style="font-variant-numeric:tabular-nums"'
        self.items.append(f"<text {attrs}>{escape(s)}</text>")

    def line(self, x1, y1, x2, y2, stroke, width=1.0):
        self.items.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke="{stroke}" stroke-width="{width}"/>')

    def path(self, d, stroke="none", width=2.0, fill="none", opacity=None):
        extra = f' fill-opacity="{opacity}"' if opacity is not None else ""
        self.items.append(f'<path d="{d}" fill="{fill}"{extra} stroke="{stroke}" stroke-width="{width}" '
                          'stroke-linejoin="round" stroke-linecap="round"/>')

    def dot(self, cx, cy, color, r=4.0):
        self.items.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{color}" '
                          f'stroke="{COL["surface"]}" stroke-width="2"/>')

    def diamond(self, cx, cy, size=6.0):
        d = f"M{cx:.1f},{cy - size:.1f}L{cx + size:.1f},{cy:.1f}L{cx:.1f},{cy + size:.1f}L{cx - size:.1f},{cy:.1f}Z"
        self.items.append(f'<path d="{d}" fill="{COL["surface"]}" stroke="{COL["ink"]}" stroke-width="2"/>')

    def render(self, height: float, title: str, desc: str) -> str:
        h = int(round(height))
        body = "\n".join(self.items)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {h}" width="{self.w}" height="{h}" '
            f'role="img" aria-labelledby="t d" font-family="{FONT}">\n'
            f"<title id=\"t\">{escape(title)}</title>\n<desc id=\"d\">{escape(desc)}</desc>\n"
            f'<rect width="{self.w}" height="{h}" fill="{COL["surface"]}"/>\n{body}\n</svg>\n'
        )


WIDE = {"name": "breed", "w": 692, "title": 17, "sub": 13.5, "tick": 12.5, "label": 13, "src": 11.5,
        "plot_h": 270, "year_step": 5}
NARROW = {"name": "smal", "w": 380, "title": 16, "sub": 13, "tick": 12, "label": 12.5, "src": 11,
          "plot_h": 290, "year_step": 10}


def header(svg: Svg, lay: dict, title: str, subtitle: str) -> float:
    y = 4.0
    for ln in wrap(title, lay["title"], lay["w"] - 8, bold=True):
        y += lay["title"] * 1.3
        svg.text(0, y, ln, size=lay["title"], fill=COL["title"], bold=True)
    for ln in wrap(subtitle, lay["sub"], lay["w"] - 8):
        y += lay["sub"] * 1.4
        svg.text(0, y, ln, size=lay["sub"], fill=COL["ink2"])
    return y


def legend(svg: Svg, lay: dict, y: float, entries: list[tuple[str, str, str]]) -> float:
    """entries: (kind 'line'|'diamond', color, label). Wraps to a new row when needed."""
    x, y = 0.0, y + lay["label"] * 1.6
    for kind, color, label in entries:
        w = 24 + text_w(label, lay["label"]) + 18
        if x > 0 and x + w > lay["w"]:
            x, y = 0.0, y + lay["label"] * 1.5
        cy = y - lay["label"] * 0.35
        if kind == "line":
            svg.line(x, cy, x + 18, cy, color, 2.5)
        else:
            svg.diamond(x + 9, cy, 5)
        svg.text(x + 24, y, label, size=lay["label"], fill=COL["ink"])
        x += w
    return y


def footer(svg: Svg, lay: dict, y: float, lines: list[str]) -> float:
    y += 8
    for para in lines:
        for ln in wrap(para, lay["src"], lay["w"] - 4):
            y += lay["src"] * 1.4
            svg.text(0, y, ln, size=lay["src"], fill=COL["muted"])
    return y + 8


class Frame:
    """A plot area with a linear x (years) and y scale, gridlines and tick labels."""

    def __init__(self, svg, lay, top, left, right, x0, x1, y_max, y_ticks, y_fmt):
        self.svg, self.lay = svg, lay
        self.top, self.bottom = top, top + lay["plot_h"]
        self.left, self.right = left, right
        self.x0, self.x1, self.y_max = x0, x1, y_max
        for t in y_ticks:
            y = self.y(t)
            svg.line(left, y, right, y, COL["axis"] if t == 0 else COL["grid"], 1)
            svg.text(left - 6, y + lay["tick"] * 0.35, y_fmt(t), size=lay["tick"], fill=COL["muted"],
                     anchor="end", tabular=True)

    def x(self, year: float) -> float:
        return self.left + (year - self.x0) / (self.x1 - self.x0) * (self.right - self.left)

    def y(self, v: float) -> float:
        return self.bottom - v / self.y_max * (self.bottom - self.top)

    def year_axis(self, years: list[int], provisional: list[int] = ()) -> float:
        for yr in years:
            self.svg.text(self.x(yr), self.bottom + self.lay["tick"] * 1.5, star(yr, provisional),
                          size=self.lay["tick"], fill=COL["muted"], anchor="middle", tabular=True)
        return self.bottom + self.lay["tick"] * 1.5

    def line(self, data: dict[int, float], color: str, area: bool = False):
        pts = [(self.x(k), self.y(v)) for k, v in sorted(data.items())]
        d = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if area:
            self.svg.path(f"{d}L{pts[-1][0]:.1f},{self.bottom:.1f}L{pts[0][0]:.1f},{self.bottom:.1f}Z",
                          fill=color, opacity=0.10)
        self.svg.path(d, stroke=color, width=2)

    def label(self, year, value, s, where="above", bold=False, anchor="middle", color=COL["grond"]):
        x, y = self.x(year), self.y(value)
        self.svg.dot(x, y, color)
        size = self.lay["label"]
        if where == "above":
            ty = y - 10
        elif where == "below":
            ty = y + 10 + size * 0.8
        else:
            raise ValueError(where)
        dx = {"start": 6, "end": 4, "middle": 0}[anchor]
        self.svg.text(x + dx, ty, s, size=size, fill=COL["ink"], bold=bold, anchor=anchor)


def year_ticks(x0: int, x1: int, step: int) -> list[int]:
    """Every `step` years from the first year; the last year is always shown."""
    ticks = list(range(x0, x1 + 1, step))
    if ticks[-1] != x1:
        if x1 - ticks[-1] < step * 0.6:
            ticks.pop()
        ticks.append(x1)
    return ticks


# --------------------------------------------------------------------------- charts


def chart_land_gdp(lay, d, refs, notes) -> tuple[str, float]:
    svg = Svg(lay["w"])
    wide = lay is WIDE
    y = header(svg, lay, "Waarde van alle grond in Nederland, in procenten van het bbp",
               "Grond onder woningen en bedrijven en landbouwgrond, eind van elk jaar")
    gutter = 140 if wide else 112
    top = y + (26 if wide else 16)
    f = Frame(svg, lay, top, 44 if wide else 40, lay["w"] - gutter, d["x0"], d["x1"], 550,
              range(0, 501, 100), lambda t: pct(t))
    f.line(d["ratio"], COL["grond"], area=True)
    x0, x1 = d["x0"], d["x1"]
    f.label(x0, d["ratio"][x0], pct(d["ratio"][x0]), where="below", anchor="start")
    f.label(d["peak_year"], d["peak"], f"{pct(d['peak'])} ({d['peak_year']})")
    f.label(d["trough_year"], d["trough"], f"{pct(d['trough'])} ({d['trough_year']})", where="below")
    f.label(x1, d["ratio"][x1], f"{pct(d['ratio'][x1])} in {d['x1_label']}", bold=True, anchor="end")
    # Reference markers in the right gutter, aligned with the 200% and 500% gridlines.
    gx = f.right + (14 if wide else 10)
    if wide:
        svg.text(gx, f.top - 8, "Ter vergelijking", size=lay["tick"], fill=COL["ink2"], bold=True)
    for value, name, val_txt in ((refs["zuid_korea_pct"], "Zuid-Korea", f"meer dan {refs['zuid_korea_pct']}%"
                                  if wide else f"> {refs['zuid_korea_pct']}%"),
                                 (refs["vs_pct"], "VS", f"ca. {refs['vs_pct']}%")):
        ry = f.y(value)
        svg.line(gx, ry, gx + 14, ry, COL["ink2"], 2)
        svg.text(gx + 20, ry + lay["label"] * 0.35, name, size=lay["label"], fill=COL["ink"], bold=True)
        svg.text(gx + 20, ry + lay["label"] * 1.6, val_txt, size=lay["label"], fill=COL["ink"])
    y = f.year_axis(year_ticks(x0, x1, lay["year_step"]), d["prov"])
    y = footer(svg, lay, y, notes)
    return svg.render(y, *d["title_desc"]), y


def chart_land_bricks(lay, d, notes) -> tuple[str, float]:
    svg = Svg(lay["w"])
    wide = lay is WIDE
    y = header(svg, lay, "Grond onder woningen en de woningen zelf",
               "Waarde in miljard euro (prijzen van elk jaar), eind van elk jaar")
    y = legend(svg, lay, y, [("line", COL["grond"], "Grond onder woningen"),
                             ("line", COL["stenen"], "Woningen zelf (de stenen)")])
    gutter = 112 if wide else 92
    top = y + 22
    f = Frame(svg, lay, top, 46 if wide else 40, lay["w"] - gutter, d["x0"], d["x1"], 2250,
              range(0, 2001, 500), lambda t: nl(t))
    f.line(d["stenen_mld"], COL["stenen"])
    f.line(d["grond_mld"], COL["grond"])
    x1 = d["x1"]
    for key, color, name in (("grond_mld", COL["grond"], "Grond"), ("stenen_mld", COL["stenen"], "Stenen")):
        v = d[key][x1]
        px, py = f.x(x1), f.y(v)
        svg.dot(px, py, color)
        svg.text(px + 10, py - 2, name, size=lay["label"], fill=COL["ink"], bold=True)
        svg.text(px + 10, py + lay["label"] * 1.15, f"€{nl(v)} mld", size=lay["label"], fill=COL["ink"])
    y = f.year_axis(year_ticks(d["x0"], x1, lay["year_step"]), d["prov"])
    y = footer(svg, lay, y, notes)
    return svg.render(y, *d["title_desc"]), y


def chart_land_share(lay, d, dnb, notes) -> tuple[str, float]:
    svg = Svg(lay["w"])
    wide = lay is WIDE
    y = header(svg, lay, "Welk deel van de woningwaarde is grond?",
               "Grond onder woningen als percentage van de waarde van grond en woningen samen")
    y = legend(svg, lay, y, [("line", COL["grond"], "CBS"),
                             ("diamond", COL["ink"], f"DNB-berekening voor {dnb['jaar']} (ESB, 2019)")])
    gutter = 80 if wide else 74
    top = y + 30
    f = Frame(svg, lay, top, 44 if wide else 40, lay["w"] - gutter, d["x0"], d["x1"], 100,
              range(0, 101, 25), lambda t: pct(t))
    f.line(d["share"], COL["grond"], area=True)
    x0, x1 = d["x0"], d["x1"]
    s = d["share"]
    f.label(x0, s[x0], pct(s[x0]), where="below", anchor="start")
    f.label(2008, s[2008], pct(s[2008]))
    f.label(BASE_YEAR, s[BASE_YEAR], pct(s[BASE_YEAR]), where="below")
    px, py = f.x(x1), f.y(s[x1])
    svg.dot(px, py, COL["grond"])
    svg.text(px + 10, py - 2, pct(s[x1]), size=lay["label"] + 1, fill=COL["ink"], bold=True)
    svg.text(px + 10, py + lay["label"] * 1.2, f"in {d['x1_label']}", size=lay["label"], fill=COL["ink"])
    # DNB cross-check marker.
    dx, dy = f.x(dnb["jaar"]), f.y(dnb["aandeel_pct"])
    svg.diamond(dx, dy, 6)
    svg.text(dx + 4, dy - 13, f"DNB: {dnb['aandeel_pct']}%", size=lay["label"], fill=COL["ink"], anchor="end")
    y = f.year_axis(year_ticks(x0, x1, lay["year_step"]), d["prov"])
    y = footer(svg, lay, y, notes)
    return svg.render(y, *d["title_desc"]), y


def bar_path(x0, y0, length, thick, r=4.0) -> str:
    """Horizontal bar: square at the baseline (left), 4px rounded data-end (right)."""
    r = min(r, length / 2, thick / 2)
    x1, y1 = x0 + length, y0 + thick
    return (f"M{x0:.1f},{y0:.1f}H{x1 - r:.1f}Q{x1:.1f},{y0:.1f} {x1:.1f},{y0 + r:.1f}"
            f"V{y1 - r:.1f}Q{x1:.1f},{y1:.1f} {x1 - r:.1f},{y1:.1f}H{x0:.1f}Z")


def chart_taxes(lay, d, notes) -> tuple[str, float]:
    svg = Svg(lay["w"])
    wide = lay is WIDE
    y = header(svg, lay, f"OZB, overdrachtsbelasting en hypotheekrenteaftrek in {d['jaar']}",
               "Miljard euro per jaar")
    bars = d["bars"]
    vmax = max(b["mln"] for b in bars) / 1000
    thick = 22
    y += 18
    if wide:
        x0, x1 = 236, lay["w"] - 100
        svg.line(x0, y, x0, y + len(bars) * 54 - 8, COL["axis"], 1)
        for b in bars:
            length = b["mln"] / 1000 / vmax * (x1 - x0)
            svg.text(0, y + 9, b["naam"], size=lay["label"], fill=COL["ink"], bold=True)
            svg.text(0, y + 9 + lay["src"] * 1.45, b["toelichting"], size=lay["src"], fill=COL["ink2"])
            svg.path(bar_path(x0, y - 6, length, thick), fill=COL["stenen"], width=0)
            svg.text(x0 + length + 8, y + 9.5, f"€{nl(b['mln'] / 1000, 1)} mld", size=lay["label"],
                     fill=COL["ink"], bold=True, tabular=True)
            y += 54
        y -= 18
    else:
        x0, x1 = 0, lay["w"] - 96
        y += 8
        for b in bars:
            svg.text(0, y, b["naam"], size=lay["label"], fill=COL["ink"], bold=True)
            svg.text(0, y + lay["src"] * 1.4, b["toelichting"], size=lay["src"], fill=COL["ink2"])
            by = y + lay["src"] * 1.4 + 8
            length = b["mln"] / 1000 / vmax * (x1 - x0)
            svg.path(bar_path(x0, by, length, thick), fill=COL["stenen"], width=0)
            svg.text(x0 + length + 8, by + 16, f"€{nl(b['mln'] / 1000, 1)} mld", size=lay["label"],
                     fill=COL["ink"], bold=True, tabular=True)
            y = by + thick + 26
        y -= 22
    y = footer(svg, lay, y + 6, notes)
    return svg.render(y, *d["title_desc"]), y


# --------------------------------------------------------------------------- main


def json_text(out: dict) -> str:
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="use the cache only, no downloads")
    ap.add_argument("--datum", type=dt.date.fromisoformat, default=dt.date.today(),
                    help="date to stamp in the outputs (YYYY-MM-DD, default today)")
    args = ap.parse_args()
    off = args.offline
    manual = tomllib.loads((HERE / "handmatig.toml").read_text("utf-8"))
    today = args.datum

    # --- downloads
    meta, years_avail = {}, {}
    for table in ("85953NED", "84550NED", "85879NED", "83642NED", "83625NED", "83131NED"):
        meta[table], years_avail[table] = table_meta(table, off)
        # 83625NED only feeds the homepage check (price vs modal income), not this page.
        meta[table]["op_pagina"] = table != "83625NED"
    sel_bal = "TypeNietFinancieleActiva,Perioden,Eindbalans_6"
    new_bal = cbs("85953NED", "TypedDataSet", "grond", off,
                  f"Sectoren eq '{SECTOR_TOTAL}' and (TypeNietFinancieleActiva eq '{LAND}' or "
                  f"TypeNietFinancieleActiva eq '{AGRI_LAND}' or TypeNietFinancieleActiva eq '{DWELLINGS}')",
                  sel_bal)
    old_bal = cbs("84550NED", "TypedDataSet", "woningen", off,
                  f"Sectoren eq '{SECTOR_TOTAL}' and (TypeNietFinancieleActiva eq '{LAND}' or "
                  f"TypeNietFinancieleActiva eq '{LAND_DWELLINGS}' or TypeNietFinancieleActiva eq '{DWELLINGS}')",
                  sel_bal + ",VolumeIndex2015100_7")
    gdp_rows = cbs("85879NED", "TypedDataSet", "bbp", off,
                   f"SoortGegevens eq '{GDP_CURRENT}' and substringof('JJ',Perioden)",
                   "SoortGegevens,Perioden,BrutoBinnenlandsProduct_2")
    tax_year = int(manual["belastingen"]["jaar"])
    ozb_rows = {code: cbs("83642NED", "TypedDataSet", f"ozb_{code}_{tax_year}", off,
                          f"GemeentelijkeHeffingenVanaf2017 eq '{code}' and Perioden eq '{tax_year}JJ00'",
                          "RegioS,Perioden,GemeentelijkeHeffingenIn1000Euro_1")
                for code in (OZB_TOTAL, OZB_HOMES, OZB_OTHER)}
    price_rows = cbs("83625NED", "TypedDataSet", "nederland", off, f"RegioS eq '{NL}  '",
                     "RegioS,Perioden,GemiddeldeVerkoopprijs_1")
    cpi_rows = cbs("83131NED", "TypedDataSet", "cpi", off,
                   f"Bestedingscategorieen eq '{CPI_ALL}  ' and substringof('JJ',Perioden)", "Bestedingscategorieen,Perioden,CPI_1")

    # --- series (mln euro unless noted)
    tna = "TypeNietFinancieleActiva"
    land = series(new_bal, tna, LAND, "Eindbalans_6")
    agri = series(new_bal, tna, AGRI_LAND, "Eindbalans_6")
    dwell_new = series(new_bal, tna, DWELLINGS, "Eindbalans_6")
    gdp = series(gdp_rows, "SoortGegevens", GDP_CURRENT, "BrutoBinnenlandsProduct_2")
    g_old = series(old_bal, tna, LAND_DWELLINGS, "Eindbalans_6")
    s_old = series(old_bal, tna, DWELLINGS, "Eindbalans_6")
    land_old = series(old_bal, tna, LAND, "Eindbalans_6")
    g_vol = series(old_bal, tna, LAND_DWELLINGS, "VolumeIndex2015100_7")
    s_vol = series(old_bal, tna, DWELLINGS, "VolumeIndex2015100_7")
    price = series(price_rows, "RegioS", NL, "GemiddeldeVerkoopprijs_1")
    cpi = series(cpi_rows, "Bestedingscategorieen", CPI_ALL, "CPI_1")

    # --- chart 1: land / GDP
    years1 = sorted(set(land) & set(gdp))
    ratio = {y: land[y] / gdp[y] * 100 for y in years1}
    x0, x1 = years1[0], years1[-1]
    prov1 = sorted(set(meta["85953NED"]["voorlopig"]) | set(meta["85879NED"]["voorlopig"]))
    peak_year = max((y for y in years1 if y <= 2010), key=ratio.get)
    trough_year = min((y for y in years1 if 2009 <= y <= 2016), key=ratio.get)
    agri_share = agri[x1] / land[x1] * 100
    ratio_ex_agri = (land[x1] - agri[x1]) / gdp[x1] * 100

    # --- charts 2 and 3: land under dwellings vs dwellings (older revision)
    years2 = sorted(set(g_old) & set(s_old))
    share = {y: g_old[y] / (g_old[y] + s_old[y]) * 100 for y in years2}
    y20, y21 = years2[0], years2[-1]
    prov2 = meta["84550NED"]["voorlopig"]
    cross_year = next(y for y in years2 if g_old[y] > s_old[y])
    for y in (2008, BASE_YEAR):
        if y not in share:
            raise SystemExit(f"expected {y} in 84550NED")

    def growth(a: dict, b0: int, b1: int) -> float:
        return (a[b1] / a[b0] - 1) * 100

    def real_unit(val: dict, vol: dict, b0: int, b1: int) -> float:
        return ((val[b1] / val[b0]) / (vol[b1] / vol[b0]) / (cpi[b1] / cpi[b0]) - 1) * 100

    # --- revision check: same year in both revisions
    rev_year = y21
    rev_land = (land_old[rev_year], land[rev_year])
    rev_dwell = (s_old[rev_year], dwell_new[rev_year])

    # --- chart 4: taxes
    def ozb_sum(code: str) -> tuple[float, int]:
        vals = [num(r["GemeentelijkeHeffingenIn1000Euro_1"]) for r in ozb_rows[code]]
        vals = [v for v in vals if v is not None]
        if len(vals) < 300:
            raise SystemExit(f"83642NED {code} {tax_year}: only {len(vals)} gemeenten with data")
        return sum(vals) / 1000, len(vals)  # 1000 euro -> mln euro

    ozb_tot, n_gem = ozb_sum(OZB_TOTAL)
    ozb_home, _ = ozb_sum(OZB_HOMES)
    ozb_other, _ = ozb_sum(OZB_OTHER)
    if abs(ozb_home + ozb_other - ozb_tot) > 0.005 * ozb_tot:
        raise SystemExit("OZB woningen + niet-woningen does not add up to the OZB total")
    prov_ozb = tax_year in meta["83642NED"]["voorlopig"]
    if years_avail["83642NED"][-1] > tax_year:
        print(f"note: CBS 83642NED now has OZB data for {years_avail['83642NED'][-1]}; update belastingen.jaar "
              "and the Miljoenennota figures in handmatig.toml", file=sys.stderr)
    ovb = manual["belastingen"]["overdrachtsbelasting"]
    hra = manual["belastingen"]["hypotheekrenteaftrek"]
    ewf = manual["belastingen"]["eigenwoningforfait"]

    # --- homepage check: average sale price vs modal income
    modal = {int(k): v for k, v in manual["cpb"]["modaal_inkomen"]["euro"].items()}
    price_year = max(y for y in price if y in modal)
    price_ratio = price[price_year] / modal[price_year]

    doucet = manual["doucet"]
    dnb19 = manual["dnb"]["esb2019"]
    dnb25 = manual["dnb"]["planbaten2025"]

    def produce(today: dt.date) -> tuple[dict, dict[Path, str]]:
        """Build the JSON and SVG texts; `today` only affects the dates printed in them."""
        svgs: dict[Path, str] = {}
        # ------------------------------------------------------------------ text values
        stamp = nl_date(today)
        x1_label = star(x1, prov1)
        y21_label = star(y21, prov2)
        t = {
            "bijgewerkt": stamp,
            # chart 1
            "grond_jaar": str(x1),
            "grond_jaar_status": "voorlopig" if x1 in prov1 else "definitief",
            "grond_totaal": mld(land[x1]),
            "grond_totaal_biljoen": f"€{nl(land[x1] / 1e6, 1)} biljoen",
            "bbp": mld(gdp[x1]),
            "grond_bbp": pct(ratio[x1]),
            "grond_bbp_keer": nl(ratio[x1] / 100, 1),
            "grond_bbp_begin_jaar": str(x0),
            "grond_bbp_begin": pct(ratio[x0]),
            "grond_bbp_piek_jaar": str(peak_year),
            "grond_bbp_piek": pct(ratio[peak_year]),
            "grond_bbp_dal_jaar": str(trough_year),
            "grond_bbp_dal": pct(ratio[trough_year]),
            "landbouwgrond": mld(agri[x1]),
            "landbouwgrond_aandeel": pct(agri_share),
            "grond_bbp_zonder_landbouw": pct(ratio_ex_agri),
            # charts 2 and 3
            "woning_jaar": str(y21),
            "woning_begin_jaar": str(y20),
            "woning_grond": mld(g_old[y21]),
            "woning_stenen": mld(s_old[y21]),
            "woning_grond_begin": mld(g_old[y20]),
            "woning_stenen_begin": mld(s_old[y20]),
            "grond_groter_dan_stenen_sinds": str(cross_year),
            "aandeel_grond": pct(share[y21]),
            "aandeel_grond_begin": pct(share[y20]),
            "aandeel_grond_2008": pct(share[2008]),
            "aandeel_grond_basis": pct(share[BASE_YEAR]),
            "basisjaar": str(BASE_YEAR),
            # 84550NED is discontinued, so the direction of these changes is fixed; the prose
            # uses unsigned values ("37% meer waard") except where the sign is the point.
            "stenen_groei_basis": pct(growth(s_old, BASE_YEAR, y21)),
            "grond_groei_basis": pct(growth(g_old, BASE_YEAR, y21)),
            "grond_factor_basis": nl(g_old[y21] / g_old[BASE_YEAR], 1),
            "stenen_volume_groei_basis": pct(growth(s_vol, BASE_YEAR, y21)),
            "cpi_groei_basis": pct(growth(cpi, BASE_YEAR, y21)),
            "stenen_reeel_per_eenheid_basis": signed_pct(real_unit(s_old, s_vol, BASE_YEAR, y21)),
            "grond_reeel_per_eenheid_basis": pct(real_unit(g_old, g_vol, BASE_YEAR, y21)),
            "revisie_jaar": str(rev_year),
            "revisie_grond_oud": mld(rev_land[0]),
            "revisie_grond_nieuw": mld(rev_land[1]),
            "revisie_grond_verschil": signed_pct_1((rev_land[1] / rev_land[0] - 1) * 100),
            "revisie_stenen_verschil": signed_pct_1((rev_dwell[1] / rev_dwell[0] - 1) * 100),
            # chart 4
            "belasting_jaar": str(tax_year),
            "miljoenennota": manual["belastingen"]["miljoenennota"],
            "ozb_totaal": mld(ozb_tot, 1),
            "ozb_woningen": mld(ozb_home, 1),
            "ozb_niet_woningen": mld(ozb_other, 1),
            "ozb_gemeenten": str(n_gem),
            "overdrachtsbelasting": mld(ovb["mln_euro"], 1),
            "hypotheekrenteaftrek": mld(hra["mln_euro"], 1),
            "eigenwoningforfait": mld(-ewf["mln_euro"], 1),
            "hypotheekrenteaftrek_netto": mld(hra["mln_euro"] + ewf["mln_euro"], 1),
            "hra_keer_ozb_woningen": nl(hra["mln_euro"] / ozb_home, 1),
            # comparisons
            "doucet_vs": f"{doucet['vs_pct']}%",
            "doucet_zuid_korea": f"{doucet['zuid_korea_pct']}%",
            "dnb_esb_jaar": str(dnb19["jaar"]),
            "dnb_esb_aandeel": f"{dnb19['aandeel_pct']}%",
            "cbs_aandeel_dnb_jaar": pct(share[dnb19["jaar"]]),
            "dnb_2025_nu": dnb25["tekst_nu"],
            "dnb_2025_eerder": f"{dnb25['eerder_pct']}%",
            # homepage check
            "huisprijs_jaar": str(price_year),
            "huisprijs": f"€{nl(price[price_year])}",
            "modaal_inkomen": f"€{nl(modal[price_year])}",
            "huisprijs_keer_modaal": nl(price_ratio, 1),
        }

        # ------------------------------------------------------------------ charts
        src_c1 = [f"Bron: CBS StatLine 85953NED (grond, eindbalans) en 85879NED (bbp, lopende prijzen). "
                  f"* {x1} voorlopig. VS en Zuid-Korea: schattingen van Lars Doucet ({doucet['datum'][:4]}).",
                  f"Bijgewerkt {stamp}. wonenisteduur.nl"]
        src_c2 = [f"Bron: CBS StatLine 84550NED (vorige reeks), eindbalans. * {y21} voorlopig. "
                  f"Latere jaren publiceert het CBS niet meer apart.", f"Bijgewerkt {stamp}. wonenisteduur.nl"]
        src_c3 = [f"Bron: CBS StatLine 84550NED; DNB: Van Hoenselaar & Mink, ESB 2019. * {y21} voorlopig.",
                  f"Bijgewerkt {stamp}. wonenisteduur.nl"]
        src_c4 = [f"Bron: CBS 83642NED (begrote OZB-opbrengst {tax_year}, {n_gem} gemeenten"
                  f"{', voorlopig' if prov_ozb else ''}); Miljoenennota 2027, tabel 3.1.7.1 "
                  f"(overdrachtsbelasting) en tabel 4.3.2 (budgettair belang hypotheekrenteaftrek).",
                  f"Bijgewerkt {stamp}. wonenisteduur.nl"]

        alt1 = (f"Lijngrafiek van de waarde van alle grond in Nederland als percentage van het bbp, {x0} tot {x1}. "
                f"Van {pct(ratio[x0])} in {x0} naar {pct(ratio[peak_year])} in {peak_year}, terug naar "
                f"{pct(ratio[trough_year])} in {trough_year} en daarna omhoog naar {pct(ratio[x1])} in {x1}. "
                f"Ter vergelijking: volgens schattingen van Lars Doucet ongeveer {doucet['vs_pct']}% in de VS en meer "
                f"dan {doucet['zuid_korea_pct']}% in Zuid-Korea.")
        alt2 = (f"Lijngrafiek van de waarde van de grond onder alle Nederlandse woningen en van de woningen zelf, in "
                f"miljard euro, {y20} tot {y21}. De stenen stijgen geleidelijk van €{nl(s_old[y20] / 1000)} naar "
                f"€{nl(s_old[y21] / 1000)} miljard. De grond stijgt van €{nl(g_old[y20] / 1000)} naar "
                f"€{nl(g_old[y21] / 1000)} miljard, met een dip tussen 2008 en {BASE_YEAR}. Sinds {cross_year} is "
                "de grond meer waard dan de stenen.")
        alt3 = (f"Lijngrafiek van het aandeel van de grond in de waarde van alle woningen, {y20} tot {y21}. Van "
                f"{pct(share[y20])} in {y20} naar {pct(share[2008])} in 2008, {pct(share[BASE_YEAR])} in {BASE_YEAR} "
                f"en {pct(share[y21])} in {y21}. Een berekening van DNB voor {dnb19['jaar']}, {dnb19['aandeel_pct']}%, "
                "ligt op de lijn.")
        bars = [
            {"naam": "OZB woningen", "toelichting": f"gemeenten, begroot {tax_year}", "mln": ozb_home},
            {"naam": "OZB niet-woningen", "toelichting": f"gemeenten, begroot {tax_year}", "mln": ozb_other},
            {"naam": "Overdrachtsbelasting", "toelichting": f"Rijk, raming {tax_year}", "mln": ovb["mln_euro"]},
            {"naam": "Hypotheekrenteaftrek", "toelichting": f"gemiste belasting, raming {tax_year}",
             "mln": hra["mln_euro"]},
        ]
        alt4 = (f"Staafdiagram met bedragen voor {tax_year} in miljard euro: "
                + "; ".join(f"{b['naam']} {nl(b['mln'] / 1000, 1)}" for b in bars)
                + ". De hypotheekrenteaftrek is geen opbrengst maar gemiste belasting.")

        charts = {
            "grond-bbp": (chart_land_gdp, {"ratio": ratio, "x0": x0, "x1": x1, "x1_label": x1_label, "prov": prov1,
                                            "peak": ratio[peak_year], "peak_year": peak_year,
                                            "trough": ratio[trough_year], "trough_year": trough_year,
                                            "title_desc": ("Waarde van alle grond in Nederland, in % van het bbp",
                                                           alt1)}, (doucet, src_c1), alt1),
            "grond-stenen": (chart_land_bricks, {"grond_mld": {y: v / 1000 for y, v in g_old.items()},
                                                  "stenen_mld": {y: v / 1000 for y, v in s_old.items()},
                                                  "x0": y20, "x1": y21, "prov": prov2,
                                                  "title_desc": ("Grond onder woningen en de woningen zelf", alt2)},
                             (src_c2,), alt2),
            "aandeel-grond": (chart_land_share, {"share": share, "x0": y20, "x1": y21, "x1_label": y21_label,
                                                  "prov": prov2,
                                                  "title_desc": ("Aandeel van de grond in de woningwaarde", alt3)},
                              (dnb19, src_c3), alt3),
            "belastingen": (chart_taxes, {"jaar": tax_year, "bars": bars,
                                          "title_desc": (f"OZB, overdrachtsbelasting en hypotheekrenteaftrek in "
                                                         f"{tax_year}", alt4)}, (src_c4,), alt4),
        }
        graphs = {}
        for slug, (fn, data, extra, alt) in charts.items():
            entry = {"alt": alt}
            for lay, suffix in ((WIDE, ""), (NARROW, "-smal")):
                svg_text, h = fn(lay, data, *extra)
                svgs[OUT_SVG / f"{slug}{suffix}.svg"] = svg_text
                key = "breed" if lay is WIDE else "smal"
                entry[key] = {"src": f"{SVG_URL}{slug}{suffix}.svg",
                              "v": hashlib.sha256(svg_text.encode()).hexdigest()[:10],
                              "w": lay["w"], "h": int(round(h))}
            graphs[slug] = entry

        # ------------------------------------------------------------------ data tables
        def mark(y, prov):
            return star(y, prov)

        graphs["grond-bbp"]["tabel"] = {
            "kop": ["Jaar", "Grond (mld €)", "Bbp (mld €)", "Grond in % van bbp"],
            "rechts": [False, True, True, True],
            "rijen": [[mark(y, prov1), nl(land[y] / 1000), nl(gdp[y] / 1000), pct(ratio[y], 1)] for y in years1],
            "noot": f"* voorlopig. Grond: CBS 85953NED, AN211, alle sectoren, eindbalans. "
                    f"Bbp: CBS 85879NED, werkelijke prijzen.",
        }
        graphs["grond-stenen"]["tabel"] = {
            "kop": ["Jaar", "Grond onder woningen (mld €)", "Woningen zelf (mld €)"],
            "rechts": [False, True, True],
            "rijen": [[mark(y, prov2), nl(g_old[y] / 1000), nl(s_old[y] / 1000)] for y in years2],
            "noot": "* voorlopig. CBS 84550NED, AN2111A en AN111, alle sectoren, eindbalans.",
        }
        graphs["aandeel-grond"]["tabel"] = {
            "kop": ["Jaar", "Aandeel grond"],
            "rechts": [False, True],
            "rijen": [[mark(y, prov2), pct(share[y], 1)] for y in years2],
            "noot": (f"* voorlopig. Aandeel = grond onder woningen / (grond onder woningen + woningen). "
                     f"DNB (ESB, 2019): {dnb19['aandeel_pct']}% in {dnb19['jaar']}."),
        }
        graphs["belastingen"]["tabel"] = {
            "kop": ["Post", "Jaar", "Bedrag (mld €)", "Bron"],
            "rechts": [False, True, True, False],
            "rijen": [
                ["OZB woningen (begroot)", str(tax_year), nl(ozb_home / 1000, 2), "CBS 83642NED"],
                ["OZB niet-woningen (begroot)", str(tax_year), nl(ozb_other / 1000, 2), "CBS 83642NED"],
                ["Overdrachtsbelasting (raming)", str(tax_year), nl(ovb["mln_euro"] / 1000, 2),
                 "Miljoenennota 2027, tabel 3.1.7.1"],
                ["Hypotheekrenteaftrek (budgettair belang, raming)", str(tax_year), nl(hra["mln_euro"] / 1000, 2),
                 "Miljoenennota 2027, tabel 4.3.2"],
                ["Eigenwoningforfait (budgettair belang, raming)", str(tax_year), nl(ewf["mln_euro"] / 1000, 2),
                 "Miljoenennota 2027, tabel 4.3.2"],
            ],
            "noot": f"OZB: som van {n_gem} gemeenten{', voorlopige cijfers' if prov_ozb else ''}. "
                    "Het eigenwoningforfait staat niet in de grafiek; het is de tegenhanger van de aftrek.",
        }

        # ------------------------------------------------------------------ provenance
        herkomst = {
            "grond_totaal": ["85953NED", f"{LAND} AN211 Grond, {SECTOR_TOTAL}, Eindbalans_6", str(x1)],
            "bbp": ["85879NED", f"{GDP_CURRENT} Werkelijke prijzen, BrutoBinnenlandsProduct_2", str(x1)],
            "grond_bbp": ["85953NED / 85879NED", "AN211 eindbalans / bbp werkelijke prijzen", f"{x0}-{x1}"],
            "landbouwgrond": ["85953NED", f"{AGRI_LAND} AN2112 Landbouwgrond, Eindbalans_6", str(x1)],
            "woning_grond": ["84550NED", f"{LAND_DWELLINGS} AN2111A Grond onder woningen, Eindbalans_6", f"{y20}-{y21}"],
            "woning_stenen": ["84550NED", f"{DWELLINGS} AN111 Woningen, Eindbalans_6", f"{y20}-{y21}"],
            "volume": ["84550NED", "VolumeIndex2015100_7 (AN111, AN2111A)", f"{BASE_YEAR}, {y21}"],
            "cpi": ["83131NED", f"{CPI_ALL} Alle bestedingen, CPI_1 (jaargemiddelde)", f"{BASE_YEAR}, {y21}"],
            "revisie": ["84550NED vs 85953NED", "AN211 en AN111, Eindbalans_6", str(rev_year)],
            "ozb": ["83642NED", f"{OZB_HOMES}/{OZB_OTHER}/{OZB_TOTAL}, GemeentelijkeHeffingenIn1000Euro_1, som gemeenten",
                    str(tax_year)],
            "overdrachtsbelasting": [ovb["bron"], ovb["url"], str(tax_year)],
            "hypotheekrenteaftrek": [hra["bron"], hra["url"], str(tax_year)],
            "eigenwoningforfait": [ewf["bron"], ewf["url"], str(tax_year)],
            "huisprijs": ["83625NED", "GemiddeldeVerkoopprijs_1, NL01", str(price_year)],
            "modaal_inkomen": [manual["cpb"]["modaal_inkomen"]["bron"], manual["cpb"]["modaal_inkomen"]["url"],
                               str(price_year)],
            "doucet": [doucet["titel"], doucet["url"], doucet["datum"]],
            "dnb_esb2019": [dnb19["titel"], dnb19["url"], str(dnb19["jaar"])],
            "dnb_2025": [dnb25["titel"], dnb25["url"], "2025"],
        }

        out = {
            "_let_op": "Gegenereerd door pipeline/cijfers/build.py. Niet met de hand aanpassen.",
            "bijgewerkt": today.isoformat(),
            "tekst": t,
            "grafieken": graphs,
            # Listed on the page in this order (most important first).
            "bronnen": [meta[k] for k in ("85953NED", "85879NED", "84550NED", "83642NED", "83131NED", "83625NED")],
            "herkomst": herkomst,
        }
        return out, svgs

    # Keep the old date (and write nothing) when only the run date would change, so a
    # scheduled run produces a diff only when CBS or handmatig.toml actually changed.
    previous = None
    if OUT_JSON.exists():
        try:
            previous = dt.date.fromisoformat(json.loads(OUT_JSON.read_text("utf-8"))["bijgewerkt"])
        except (ValueError, KeyError, TypeError):
            previous = None
    if previous and previous != today:
        out_prev, svgs_prev = produce(previous)
        if (json_text(out_prev) == OUT_JSON.read_text("utf-8")
                and all(f.exists() and f.read_text("utf-8") == s for f, s in svgs_prev.items())):
            print(f"numbers unchanged since {previous.isoformat()}; nothing written")
            return
    out, svgs = produce(today)
    t = out["tekst"]
    OUT_SVG.mkdir(parents=True, exist_ok=True)
    for f, s in svgs.items():
        f.write_text(s, "utf-8")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json_text(out), "utf-8")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {len(svgs)} SVGs in {OUT_SVG.relative_to(ROOT)}/")
    for k in ("grond_totaal", "grond_bbp", "aandeel_grond", "ozb_totaal", "huisprijs_keer_modaal"):
        print(f"  {k}: {t[k]}")


if __name__ == "__main__":
    main()
