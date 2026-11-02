# Amsterdam: grondwaarde, parkeren en een OZB-verschuiving

Pipeline behind [/amsterdam/](https://wonenisteduur.nl/amsterdam/). It estimates a
land price per buurt from open data (Lars Doucet's "simplest viable method"),
values surface parking land, and models a revenue-neutral shift of the OZB on
woningen from total value to land. The method in Dutch, with every parameter, is
on [/amsterdam/methode/](https://wonenisteduur.nl/amsterdam/methode/).

All results are **estimates**, not official values.

## Run

Requires [uv](https://docs.astral.sh/uv/). Each script is a PEP 723 script. Run
them from this folder (`pipeline/amsterdam/`), in this order:

```bash
export AMS_CACHE=/path/to/cache   # raw downloads (~9 GB incl. BAG); default ./cache (gitignored)
uv run 01_fetch.py     # downloads: CBS, CVDR, CBS grid, DKK, BGT, OSM, BAG bulk
uv run 02_prepare.py   # parse + clip to the gemeente -> cache/work/*.parquet
uv run 03_land.py      # A: land price per buurt
uv run 04_parking.py   # B: surface parking land
uv run 05_ozb.py       # C: OZB shift, woningen
uv run 06_publish.py   # D: data/amsterdam/*.json, static/amsterdam/{data,grafieken,*.png}
uv run 07_grondstaffel.py  # check: compare with the municipality's grondstaffel (adds gs_* keys)
uv run 08_denhaag.py       # check: the same comparison in Den Haag (adds dh_* keys), see below
```

Every number on the site pages comes from `data/amsterdam/cijfers.json`.
`06_publish.py` rewrites that file, and 07 and 08 add their keys to it, so run
them after 06. The grondstaffel tables are already committed as CSV; see below
for how to extract them again.

All parameters live in `params.toml`. Downloaded files are only parsed, never executed.

## Outputs (`output/`, committed)

| File | Content |
|---|---|
| `buurt_grondprijs.csv` / `.geojson` | per buurt: WOZ, land share (raw and shrunk, low/central/high), land price per m² parcel, land value per m² floor area, rate source, checks |
| `buurt_parkeren.csv` | per buurt: off-street lot and on-street bay area and value |
| `parkeerterreinen.geojson` | off-street surface lots with descriptive name and value |
| `top20_parkeerterreinen.csv` | 20 most valuable lots (buurten with own estimate) |
| `ozb_buurt.csv`, `ozb_buurt_type.csv` | typical OZB change per buurt and per buurt x housing type |
| `vergelijking_grondstaffel.csv` | per buurt (mostly grondgebonden): official land price from the grondstaffel vs ours |
| `denhaag/` | the same land price estimate for Den Haag, and its comparison with Den Haag's grondstaffel |
| `samenvatting_*.json` | all aggregate numbers used on the site |

No per-dwelling or per-address output is written.

## Data and licences

CBS (CC BY 4.0), Kadaster Kadastrale kaart via PDOK (CC BY 4.0, credit "Kadaster"),
BAG (public domain), BGT (CC0), OpenStreetMap (ODbL), gemeente Amsterdam CVDR texts,
gemeente Amsterdam Verantwoordingsdocument WOZ 2024/2025 and gemeente Den Haag
Bijlage Grondstaffels 2024-2026 (published without a copyright reservation in the
documents, art. 15b Auteurswet; only the area-level grondstaffel tables).
Not used, on purpose: WOZ-waardeloket, per-address WOZ, BRK owner data,
restricted Amsterdam WOZ/erfpacht APIs. Lots are named by type and location,
never by owner or brand.

## The municipality's grondstaffel

A Woo request for the grondstaffels was refused (art. 40 Wet WOZ sets aside the
Woo), but Amsterdam publishes them in its yearly Verantwoordingsdocument WOZ.
amsterdam.nl blocks scripted downloads, so the tables were extracted once from
PDFs downloaded in a browser and committed to `input/grondstaffel/`:

```bash
uv run grondstaffel_pdf.py --vd2024 "Verantwoordingsdocument WOZ 2024.pdf" --vd2025 "Verantwoordingsdocument WOZ 2025.pdf"
```

They are used only as a check (`07_grondstaffel.py`), not as a replacement for
the estimate: they cover grondgebonden woningen only (apartments get no land
part), and the split between woning and grond moves a lot between model years.
Our land prices come out about twice the official ones in mostly-grondgebonden
buurten, with a similar ranking of buurten. See the method page.

## Den Haag as a cross-check

To see whether that factor of two is particular to Amsterdam's model, steps
01-03 also run for Den Haag, with the same parameters (`params-denhaag.toml`
only changes the area). Den Haag publishes its grondstaffels in a yearly
"Bijlage Grondstaffels" and allows scripted downloads, so the extraction
downloads the PDFs itself:

```bash
AMS_GEMEENTE=denhaag uv run 01_fetch.py     # cbs, grid, dkk, bag (shares the BAG file with Amsterdam)
AMS_GEMEENTE=denhaag uv run 02_prepare.py
AMS_GEMEENTE=denhaag uv run 03_land.py      # -> output/denhaag/
uv run grondstaffel_denhaag.py              # -> input/grondstaffel/denhaag/grondstaffel.csv
uv run 08_denhaag.py
```

The Den Haag cache lives in `$AMS_CACHE/denhaag/`. Steps 04-08 refuse to run
for another gemeente: they write the Amsterdam site data.

## Colours

Land value: one-hue sage ramp (`06_publish.py`, `SEQ`), monotone in OKLCH lightness.
OZB change: blue (down) / orange (up) with a grey midpoint (`DIV`). The two poles
pass the dataviz validator (CVD ΔE 21.9 on the site background).

## Vendor

`static/amsterdam/vendor/maplibre-gl-5.24.0/`: MapLibre GL JS 5.24.0 from npm
(integrity checked), BSD-3-Clause, `LICENSE.txt` included. The source-map comment
was removed so browsers do not request a missing `.map` file.
